"""
Contrato da triagem por LLM: monta o prompt (uma chamada por artigo, com todos
os criterios), o JSON schema da resposta, interpreta a resposta e decide se o
artigo e selecionado.

Fonte unica para a aplicacao (scripts/analisys_LLM.py) e para a avaliacao
contra o gabarito humano (LLMs_Analysis/code/run_screening.py): mudar o prompt
aqui muda o que a ferramenta faz e o que os estudos medem.
"""
import json
from pathlib import Path
from typing import Any


CRITERIA_KEY = "Criteria"
ARTICLES_KEY = "articles"
INCLUSION_KEY = "Inclusion"
EXCLUSION_KEY = "Exclusion"

ANSWER_YES = "Yes"
ANSWER_NO = "No"
ANSWER_ERROR = "error"

NOT_AVAILABLE = "not available"
MAX_TITLE_CHARS = 300
MAX_ABSTRACT_CHARS = 2000

# Metadados enviados alem de titulo e abstract, na ordem em que aparecem no
# prompt. Vao todos, para todos os criterios.
METADATA_FIELDS = (
    "year",
    "language",
    "venue",
    "keywords",
    "pages",
    "numpages",
    "open_access",
    "citationCount",
)


SYSTEM_INSTRUCTIONS = """You are an expert researcher screening studies for a systematic literature review.
For a single article, decide whether each inclusion and exclusion criterion given by the user is satisfied.

DECISION RULES
- Judge every criterion independently, by its own wording. The answer to one criterion never constrains the answer to another.
- Use only the article data provided. The title and abstract are the main evidence. The other metadata fields (such as year, language, venue, keywords, pages, open access, and citation count) are evidence too, and must be used whenever a criterion refers to them.
- Metadata fields that are not listed were not available for this article. Never invent data and never rely on outside knowledge about the article.
- Inclusion criterion: answer "Yes" when the article satisfies it, "No" otherwise.
- Exclusion criterion: answer "Yes" when the criterion applies to the article, which means the article must be excluded for that reason, and "No" otherwise.
- Aim for the correct answer on every criterion. Weigh the evidence and choose the answer it supports best. Do not default to "Yes" or to "No" when the article data is thin.
- The wording of the abstract, the venue and the page count usually reveal the type of study and how it was conducted; read those signals instead of guessing.
- Think through the criteria carefully before answering, but do not include your reasoning in the output.
- Before you answer, check each criterion once more against the article data.
"""

OUTPUT_FORMAT = """
OUTPUT FORMAT
- Return one JSON object and nothing else: no explanation, no reasoning, no confidence, no markdown and no code fences.
- The object has exactly one top-level key: "criteria".
- "criteria" holds exactly the criterion IDs given by the user, each with the value "Yes" or "No".
- "Yes" and "No" are the only accepted values. Never answer with another word and never leave a criterion out."""


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_articles_json(path: str | Path) -> dict[str, Any]:
    articles_path = Path(path)
    return json.loads(articles_path.read_text(encoding="utf-8-sig"))


def extract_criteria(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    criteria = data.get(CRITERIA_KEY)

    if not isinstance(criteria, dict):
        raise ValueError(f"Chave obrigatoria nao encontrada: {CRITERIA_KEY}")

    inclusion = criteria.get(INCLUSION_KEY)
    exclusion = criteria.get(EXCLUSION_KEY)

    if not isinstance(inclusion, dict):
        raise ValueError(f"Chave obrigatoria nao encontrada: {CRITERIA_KEY}.{INCLUSION_KEY}")

    if not isinstance(exclusion, dict):
        raise ValueError(f"Chave obrigatoria nao encontrada: {CRITERIA_KEY}.{EXCLUSION_KEY}")

    return {
        INCLUSION_KEY: inclusion,
        EXCLUSION_KEY: exclusion,
    }


def criteria_from_text(
    criterios_inclusao: str,
    criterios_exclusao: str,
) -> dict[str, dict[str, str]]:
    return {
        INCLUSION_KEY: _criteria_lines_to_dict(criterios_inclusao, "IC"),
        EXCLUSION_KEY: _criteria_lines_to_dict(criterios_exclusao, "EC"),
    }


def expected_criteria_ids(criteria: dict[str, dict[str, str]]) -> list[str]:
    return [
        *criteria.get(INCLUSION_KEY, {}).keys(),
        *criteria.get(EXCLUSION_KEY, {}).keys(),
    ]


def format_criteria(criteria_group: dict[str, str]) -> str:
    if not criteria_group:
        return "- none"

    return "\n".join(
        f"- {criterion_id}: {description}"
        for criterion_id, description in criteria_group.items()
    )


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in ("", "-")
    if isinstance(value, (list, dict)):
        return not value
    return False


def _truncate(value: Any, limit: int) -> str:
    text = normalize_text(value)
    return f"{text[:limit]}..." if len(text) > limit else text


def _stringify_metadata_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, list):
        normalized_items = []
        for item in value:
            if isinstance(item, dict):
                name = normalize_text(item.get("name"))
                normalized_items.append(name or json.dumps(item, ensure_ascii=False))
            else:
                normalized_items.append(normalize_text(item))

        normalized_items = [item for item in normalized_items if item]
        return ", ".join(normalized_items) if normalized_items else NOT_AVAILABLE

    return normalize_text(value) or NOT_AVAILABLE


def format_article(article: dict[str, Any]) -> str:
    title = article.get("title")
    abstract = article.get("abstract")
    lines = [
        f"- title: {NOT_AVAILABLE if _is_missing(title) else _truncate(title, MAX_TITLE_CHARS)}",
        f"- abstract: {NOT_AVAILABLE if _is_missing(abstract) else _truncate(abstract, MAX_ABSTRACT_CHARS)}",
    ]

    for field_name in METADATA_FIELDS:
        value = article.get(field_name)
        if field_name == "citationCount" and _is_missing(value):
            value = article.get("citations_count")
        # Campo ausente fica fora do prompt; o system prompt avisa que campo
        # nao listado nao estava disponivel.
        if not _is_missing(value):
            lines.append(f"- {field_name}: {_stringify_metadata_value(value)}")

    return "\n".join(lines)


def _system_prompt(extra_prompt: str = "") -> str:
    extra = normalize_text(extra_prompt)
    extra_section = f"\nADDITIONAL INSTRUCTIONS FROM THE REVIEWER\n{extra}\n" if extra else ""
    return f"{SYSTEM_INSTRUCTIONS}{extra_section}{OUTPUT_FORMAT}"


def _user_prompt(article: dict[str, Any], criteria: dict[str, dict[str, str]]) -> str:
    output_shape = json.dumps(
        {"criteria": {criterion_id: "Yes|No" for criterion_id in expected_criteria_ids(criteria)}},
        separators=(",", ":"),
    )
    return (
        'INCLUSION CRITERIA (answer "Yes" when the article satisfies the criterion)\n'
        f"{format_criteria(criteria.get(INCLUSION_KEY, {}))}\n\n"
        'EXCLUSION CRITERIA (answer "Yes" when the criterion applies and the article must be excluded)\n'
        f"{format_criteria(criteria.get(EXCLUSION_KEY, {}))}\n\n"
        f"ARTICLE\n{format_article(article)}\n\n"
        f"Answer with this exact JSON shape, replacing each Yes|No with one of the two values:\n{output_shape}"
    )


def generate_messages(
    article: dict[str, Any],
    criteria: dict[str, dict[str, str]],
    extra_prompt: str = "",
) -> list[dict[str, str]]:
    """Mensagens no formato chat (role/content). Instrucoes fixas ficam no
    system; criterios e artigo no user."""
    return [
        {"role": "system", "content": _system_prompt(extra_prompt)},
        {"role": "user", "content": _user_prompt(article, criteria)},
    ]


def response_schema(criteria: dict[str, dict[str, str]]) -> dict[str, Any]:
    criterion_ids = expected_criteria_ids(criteria)
    return {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "object",
                "properties": {
                    criterion_id: {"type": "string", "enum": [ANSWER_YES, ANSWER_NO]}
                    for criterion_id in criterion_ids
                },
                "required": criterion_ids,
                "additionalProperties": False,
            }
        },
        "required": ["criteria"],
        "additionalProperties": False,
    }


def _normalize_answer(value: Any) -> str:
    normalized = normalize_text(value).lower()

    if normalized in {"yes", "sim"}:
        return ANSWER_YES

    if normalized in {"no", "nao", "não"}:
        return ANSWER_NO

    return ANSWER_ERROR


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        raise ValueError("JSON nao encontrado na resposta")

    return json.loads(text[start:end + 1])


def parse_criteria_response(text: str, criteria: dict[str, dict[str, str]]) -> dict[str, str]:
    """Resposta da LLM -> {criterio: "Yes" | "No" | "error"}. Nunca levanta:
    resposta invalida ou criterio ausente vira "error"."""
    criterion_ids = expected_criteria_ids(criteria)

    try:
        data = _extract_json_object(normalize_text(text))
    except ValueError:
        return {criterion_id: ANSWER_ERROR for criterion_id in criterion_ids}

    raw_criteria = data.get("criteria") if isinstance(data.get("criteria"), dict) else data
    return {
        criterion_id: _normalize_answer(raw_criteria.get(criterion_id))
        for criterion_id in criterion_ids
    }


def is_selected(criteria: dict[str, dict[str, str]], results: dict[str, str]) -> bool | None:
    """Selecionado quando todo criterio de inclusao e "Yes" e nenhum de exclusao
    e "Yes". None quando algum criterio ficou sem resposta valida."""
    if any(results.get(criterion_id) not in (ANSWER_YES, ANSWER_NO) for criterion_id in expected_criteria_ids(criteria)):
        return None

    all_inclusion = all(results[criterion_id] == ANSWER_YES for criterion_id in criteria.get(INCLUSION_KEY, {}))
    any_exclusion = any(results[criterion_id] == ANSWER_YES for criterion_id in criteria.get(EXCLUSION_KEY, {}))
    return all_inclusion and not any_exclusion


def _criteria_lines_to_dict(text: str, prefix: str) -> dict[str, str]:
    criteria = {}

    for index, line in enumerate(_split_lines(text), start=1):
        criterion_id = f"{prefix}{index}"
        criteria[criterion_id] = _strip_existing_numbering(line)

    return criteria


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _strip_existing_numbering(line: str) -> str:
    stripped = line.strip()
    parts = stripped.split(".", 1)

    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[1].strip()

    return stripped
