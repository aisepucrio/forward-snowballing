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


def format_criteria(criteria_group: dict[str, str]) -> str:
    return "\n".join(
        f"- {criterion_id}: {description}"
        for criterion_id, description in criteria_group.items()
    )


def build_results_schema(criteria: dict[str, dict[str, str]]) -> str:
    criteria_ids = [
        *criteria[INCLUSION_KEY].keys(),
        *criteria[EXCLUSION_KEY].keys(),
    ]

    lines = [
        '    "results": {',
    ]

    for index, criterion_id in enumerate(criteria_ids):
        comma = "," if index < len(criteria_ids) - 1 else ""
        lines.append(f'      "{criterion_id}": "Yes|No"{comma}')

    lines.extend([
        "    },",
        '    "Decision": {',
        '      "decision": "inclusion|exclusion"',
        "    }",
    ])

    return "\n".join(lines)


def generate_prompt(
    title: str,
    abstract: str,
    criteria: dict[str, dict[str, str]],
) -> str:
    inclusion_criteria = format_criteria(criteria[INCLUSION_KEY])
    exclusion_criteria = format_criteria(criteria[EXCLUSION_KEY])
    results_schema = build_results_schema(criteria)

    return f"""You are an expert researcher conducting a Systematic Review.
Evaluate the article based on the inclusion and exclusion criteria.

INCLUSION CRITERIA (mark Yes/No)
{inclusion_criteria}

EXCLUSION CRITERIA (mark Yes/No)
{exclusion_criteria}

ARTICLE TO ANALYZE:
- title: {normalize_text(title)}
- abstract: {normalize_text(abstract)}

EXACT OUTPUT FORMAT (JSON):
{{
  "title": "<repeat the article title>",
{results_schema}
}}

Rules:
- Use only "Yes" or "No" in the result for each criterion.
- If any inclusion criterion is marked "No", the decision must be "exclusion". STOP and return the results json.
- If any exclusion criterion is marked "Yes", the decision must be "exclusion". STOP and return the results json.
- Only if all inclusion criteria are "Yes" and all exclusion criteria are "No", the decision can be "inclusion".
- Do not include any keys other than the requested ones.
- Return only the JSON, without any markdown or extra text.
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
