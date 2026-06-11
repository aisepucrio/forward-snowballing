import json
from pathlib import Path
from typing import Any


CRITERIA_KEY = "Criteria"
ARTICLES_KEY = "articles"
INCLUSION_KEY = "Inclusion"
EXCLUSION_KEY = "Exclusion"


NOT_AVAILABLE = "not available"


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


def _stringify_metadata_value(value: Any) -> str:
    if value is None:
        return NOT_AVAILABLE

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else NOT_AVAILABLE

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


def _format_article_metadata(article: dict[str, Any]) -> str:
    metadata_fields = [
        ("paperId", article.get("paperId")),
        ("title", article.get("title")),
        ("abstract", article.get("abstract")),
        ("authors", article.get("authors")),
        ("year", article.get("year")),
        ("venue", article.get("venue")),
        ("citationCount", article.get("citationCount", article.get("citations_count"))),
        ("language", article.get("language")),
        ("pages", article.get("pages")),
        ("numpages", article.get("numpages")),
        ("open_access", article.get("open_access")),
        ("keywords", article.get("keywords")),
    ]

    return "\n".join(
        f"- {field_name}: {_stringify_metadata_value(field_value)}"
        for field_name, field_value in metadata_fields
    )


def generate_prompt(
    article: dict[str, Any],
    criteria: dict[str, dict[str, str]],
    extra_prompt: str = "",
) -> str:
    inclusion_criteria = format_criteria(criteria[INCLUSION_KEY])
    exclusion_criteria = format_criteria(criteria[EXCLUSION_KEY])
    criteria_schema = _format_criteria_schema(criteria)
    article_metadata = _format_article_metadata(article)
    extra_section = f"ADDITIONAL INSTRUCTIONS\n{extra_prompt.strip()}\n\n" if extra_prompt and extra_prompt.strip() else ""

    return f"""{extra_section}You are an expert researcher conducting a Systematic Review.
Your task is to classify the article against each inclusion and exclusion criterion.

Think through the criteria carefully before answering, but do not include your reasoning in the output.

The examples below illustrate the decision process only.
Do not reuse the example criteria when analyzing the real article.

EXAMPLE CRITERIA

INCLUSION CRITERIA
- IC1: The article is a primary empirical study.
- IC2: The article evaluates an intervention, method, technique, or phenomenon related to the review topic.

EXCLUSION CRITERIA
- EC1: The article is a literature review, mapping study, editorial, tutorial, or opinion paper.
- EC2: The article is outside the review topic.

EXAMPLE ARTICLE:
- title: Empirical evaluation of a method in the target research area
- abstract: This paper presents a primary empirical study evaluating a method related to the target research area. The authors collect data, describe the study design, report results, and discuss implications for the investigated topic.

EXPECTED OUTPUT:
{{"criteria":{{"IC1":"Yes","IC2":"Yes","EC1":"No","EC2":"No"}}}}

EXAMPLE ARTICLE:
- title: A review of methods in the target research area
- abstract: This paper reviews and summarizes previously published studies about methods related to the target research area. It organizes existing literature, compares prior findings, and identifies open research challenges, but it does not present a new primary empirical study.

EXPECTED OUTPUT:
{{"criteria":{{"IC1":"No","IC2":"Yes","EC1":"Yes","EC2":"No"}}}}

REAL CRITERIA

INCLUSION CRITERIA
{inclusion_criteria}

EXCLUSION CRITERIA
{exclusion_criteria}

REAL ARTICLE
{article_metadata}

CLASSIFICATION RULES:
- For each inclusion criterion, return "Yes" if the article satisfies it; otherwise return "No".
- For each exclusion criterion, return "Yes" if the article satisfies it; otherwise return "No".
- When evidence is ambiguous, incomplete, or only weakly implied, favor selection: use "Yes" for ambiguous inclusion criteria and "No" for ambiguous exclusion criteria.

OUTPUT:
- Return only valid compact JSON.
- The JSON must contain exactly one top-level key: "criteria".
- The "criteria" object must contain exactly these criterion keys and values "Yes" or "No":
{criteria_schema}
- Do not include explanations, reasoning, confidence, markdown, or extra text.
"""


def build_prompt_for_article(
    article: dict[str, Any],
    articles_json_path: str | Path,
) -> str:
    data = load_articles_json(articles_json_path)
    criteria = extract_criteria(data)
    return generate_prompt(article, criteria)


def build_prompts_from_articles_json(articles_json_path: str | Path) -> list[str]:
    data = load_articles_json(articles_json_path)
    criteria = extract_criteria(data)
    articles = data.get(ARTICLES_KEY, [])

    if not isinstance(articles, list):
        raise ValueError(f"Chave obrigatoria deve ser uma lista: {ARTICLES_KEY}")

    return [
        generate_prompt(
            article=article,
            criteria=criteria,
        )
        for article in articles
    ]


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


def _format_criteria_schema(criteria: dict[str, dict[str, str]]) -> str:
    ids = expected_criteria_ids(criteria)

    if not ids:
        return "{}"

    return json.dumps({criterion_id: "Yes or No" for criterion_id in ids})
