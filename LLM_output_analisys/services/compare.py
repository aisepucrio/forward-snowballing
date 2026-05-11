import json
from pathlib import Path
from typing import Any


RESULTS_KEY = "results"
TITLE_KEY = "title"
SELECTED_KEY = "selected"


def normalize_title(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_selected(value: Any) -> int:
    normalized = str(value).strip().lower()
    if normalized in {"1", "yes", "y", "sim", "true", "inclusion", "include", "included"}:
        return 1
    return 0


def read_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}

    text = json_path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return {}
    return json.loads(text)


def write_text(content: str, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def load_results(path: str | Path) -> tuple[dict[str, int], list[str]]:
    data = read_json(path)
    results = data.get(RESULTS_KEY, [])

    if not isinstance(results, list):
        raise ValueError(f"Chave obrigatoria deve ser uma lista: {RESULTS_KEY}")

    results_by_title: dict[str, int] = {}
    duplicated_titles: list[str] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        title = normalize_title(item.get(TITLE_KEY))
        if not title:
            continue

        if title in results_by_title:
            duplicated_titles.append(title)

        results_by_title[title] = normalize_selected(item.get(SELECTED_KEY))

    return results_by_title, duplicated_titles


def safe_division(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def calculate_metrics(
    original_results: dict[str, int],
    llm_results: dict[str, int],
) -> dict[str, Any]:
    original_titles = set(original_results)
    llm_titles = set(llm_results)
    common_titles = original_titles & llm_titles

    true_positives = [
        title for title in common_titles
        if original_results[title] == 1 and llm_results[title] == 1
    ]
    false_positives = [
        title for title in common_titles
        if original_results[title] == 0 and llm_results[title] == 1
    ]
    false_negatives = [
        title for title in common_titles
        if original_results[title] == 1 and llm_results[title] == 0
    ]
    true_negatives = [
        title for title in common_titles
        if original_results[title] == 0 and llm_results[title] == 0
    ]

    precision = safe_division(len(true_positives), len(true_positives) + len(false_positives))
    recall = safe_division(len(true_positives), len(true_positives) + len(false_negatives))
    f1_score = safe_division(2 * precision * recall, precision + recall)
    coverage = safe_division(len(common_titles), len(original_titles))

    return {
        "total_original": len(original_titles),
        "total_llm": len(llm_titles),
        "total_compared": len(common_titles),
        "coverage": coverage,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "missing_in_llm": sorted(original_titles - llm_titles),
        "extra_in_llm": sorted(llm_titles - original_titles),
        "llm_included_original_not_included": sorted(false_positives),
        "original_included_llm_not_included": sorted(false_negatives),
        "precision": precision,
        "recall": recall,
        "f1_score": f1_score,
    }


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_title_list(titles: list[str]) -> str:
    if not titles:
        return "- Nenhum"

    return "\n".join(f"- {title}" for title in titles)


def build_report(
    metrics: dict[str, Any],
    original_duplicates: list[str],
    llm_duplicates: list[str],
) -> str:
    lines = [
        "Comparacao de resultados",
        "",
        "Resumo",
        f"- Total de artigos no original: {metrics['total_original']}",
        f"- Total de artigos no resultado da LLM: {metrics['total_llm']}",
        f"- Total de artigos comparados: {metrics['total_compared']}",
        f"- Cobertura da LLM: {format_percent(metrics['coverage'])}",
        "",
        "Metricas da LLM considerando o original como gabarito",
        f"- Precision: {metrics['precision']:.4f}",
        f"- Recall: {metrics['recall']:.4f}",
        f"- F1-score: {metrics['f1_score']:.4f}",
        "",
        "Matriz de comparacao",
        f"- True positives: {len(metrics['true_positives'])}",
        f"- False positives: {len(metrics['false_positives'])}",
        f"- False negatives: {len(metrics['false_negatives'])}",
        f"- True negatives: {len(metrics['true_negatives'])}",
        "",
        "Artigos incluidos pela LLM e nao pelo original",
        format_title_list(metrics["llm_included_original_not_included"]),
        "",
        "Artigos incluidos pelo original e nao pela LLM",
        format_title_list(metrics["original_included_llm_not_included"]),
        "",
        "Artigos do original sem resultado da LLM",
        format_title_list(metrics["missing_in_llm"]),
        "",
        "Artigos presentes na LLM e ausentes no original",
        format_title_list(metrics["extra_in_llm"]),
    ]

    if original_duplicates or llm_duplicates:
        lines.extend([
            "",
            "Avisos",
            "Titulos duplicados no original:",
            format_title_list(sorted(set(original_duplicates))),
            "",
            "Titulos duplicados no resultado da LLM:",
            format_title_list(sorted(set(llm_duplicates))),
        ])

    return "\n".join(lines) + "\n"


def compare_results_json(
    original_results_path: str | Path,
    llm_results_path: str | Path,
    output_txt_path: str | Path,
) -> dict[str, Any]:
    original_results, original_duplicates = load_results(original_results_path)
    llm_results, llm_duplicates = load_results(llm_results_path)

    metrics = calculate_metrics(original_results, llm_results)
    report = build_report(metrics, original_duplicates, llm_duplicates)
    write_text(report, output_txt_path)

    return metrics


if __name__ == "__main__":
    compare_results_json(
        original_results_path="data/study1/results.json",
        llm_results_path="data/study1/results_llm.json",
        output_txt_path="data/study1/comparison.txt",
    )
