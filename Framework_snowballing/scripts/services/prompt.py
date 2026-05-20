import json
from pathlib import Path
from typing import Any


CRITERIA_KEY = "Criteria"
ARTICLES_KEY = "articles"
INCLUSION_KEY = "Inclusion"
EXCLUSION_KEY = "Exclusion"


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


def generate_prompt(
    title: str,
    abstract: str,
    criteria: dict[str, dict[str, str]],
) -> str:
    inclusion_criteria = format_criteria(criteria[INCLUSION_KEY])
    exclusion_criteria = format_criteria(criteria[EXCLUSION_KEY])
    criteria_schema = _format_criteria_schema(criteria)

    return f"""You are an expert researcher conducting a Systematic Review.
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
- title: {normalize_text(title)}
- abstract: {normalize_text(abstract)}

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
    title: str,
    abstract: str,
    articles_json_path: str | Path,
) -> str:
    data = load_articles_json(articles_json_path)
    criteria = extract_criteria(data)
    return generate_prompt(title, abstract, criteria)


def build_prompts_from_articles_json(articles_json_path: str | Path) -> list[str]:
    data = load_articles_json(articles_json_path)
    criteria = extract_criteria(data)
    articles = data.get(ARTICLES_KEY, [])

    if not isinstance(articles, list):
        raise ValueError(f"Chave obrigatoria deve ser uma lista: {ARTICLES_KEY}")

    return [
        generate_prompt(
            title=article.get("title", ""),
            abstract=article.get("abstract", ""),
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
