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


def generate_prompt(
    title: str,
    abstract: str,
    criteria: dict[str, dict[str, str]],
) -> str:
    inclusion_criteria = format_criteria(criteria[INCLUSION_KEY])
    exclusion_criteria = format_criteria(criteria[EXCLUSION_KEY])

    return f"""You are an expert researcher conducting a Systematic Review.
Your task is to decide whether the article should be selected.

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
1

EXAMPLE ARTICLE:
- title: A review of methods in the target research area
- abstract: This paper reviews and summarizes previously published studies about methods related to the target research area. It organizes existing literature, compares prior findings, and identifies open research challenges, but it does not present a new primary empirical study.

EXPECTED OUTPUT:
0

REAL CRITERIA

INCLUSION CRITERIA
{inclusion_criteria}

EXCLUSION CRITERIA
{exclusion_criteria}

REAL ARTICLE
- title: {normalize_text(title)}
- abstract: {normalize_text(abstract)}

DECISION RULES:
- Return 1 if the article satisfies all inclusion criteria and no exclusion criterion is satisfied.
- Return 0 if any inclusion criterion is not satisfied.
- Return 0 if any exclusion criterion is satisfied.
- Return 1 when the evidence is ambiguous, incomplete, or only weakly implied.

OUTPUT:
- Return only one character: 0 or 1.
- Do not include explanations, reasoning, criterion labels, confidence, markdown, JSON, or extra text.
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
