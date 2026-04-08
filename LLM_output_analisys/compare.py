import csv
import json
import re
import unicodedata
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "source.csv"
JSON_PATH = BASE_DIR / "resultados.json"
OUTPUT_TXT_PATH = BASE_DIR / "comparacao_resultados.txt"


def normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def csv_selected_to_bool(value: str) -> bool:
    return normalize_text(value) in {"yes", "sim", "true", "1", "incluir", "inclusao"}


def json_decision_to_bool(value: str) -> bool:
    return normalize_text(value) in {"inclusao", "incluir", "include", "included", "yes", "sim", "true", "1"}


def load_csv_articles(path: Path) -> dict:
    articles = {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = (row.get("Title") or "").strip()
            if not title:
                continue

            key = normalize_text(title)
            articles[key] = {
                "title": title,
                "included": csv_selected_to_bool(row.get("Selected", "")),
            }

    return articles


def load_json_results(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    results = {}
    for item in data:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        resumo = item.get("ResumoDecisao") or item.get("resumoDecisao") or {}
        decisao = resumo.get("decisao", "")

        key = normalize_text(title)
        results[key] = {
            "title": title,
            "included": json_decision_to_bool(decisao),
        }

    return results


def build_report(csv_articles: dict, json_results: dict) -> str:
    total_csv = len(csv_articles)
    csv_included = {k for k, v in csv_articles.items() if v["included"]}
    json_included = {k for k, v in json_results.items() if v["included"]}

    included_by_json_not_csv = sorted(json_included - csv_included)
    included_by_csv_not_json = sorted(csv_included - json_included)

    matched = 0
    for key, csv_article in csv_articles.items():
        csv_value = csv_article["included"]
        json_value = json_results.get(key, {}).get("included", False)
        if csv_value == json_value:
            matched += 1

    alignment = (matched / total_csv * 100) if total_csv else 0.0

    lines = [
        f"Quantos artigos haviam no total do csv: {total_csv}",
        f"Quantos artigos foram incluido pelo csv (coluna Selected): {len(csv_included)}",
        f"Quantos artigos foram incluidos pelo json (campo ResumoDecisao.decisao): {len(json_included)}",
        f"Quantos artigos foram incluidos pelo json e nao pelo csv: {len(included_by_json_not_csv)}",
        f"Quantos artigos foram incluido pelo csv e nao pelo json: {len(included_by_csv_not_json)}",
        f"Porcentagem de alinhamento: {alignment:.2f}%",
        "",
        "Titulos incluidos pelo json e nao pelo csv:",
    ]

    if included_by_json_not_csv:
        lines.extend(f"- {json_results[key]['title']}" for key in included_by_json_not_csv)
    else:
        lines.append("- Nenhum")

    lines.append("")
    lines.append("Titulos incluidos pelo csv e nao pelo json:")

    if included_by_csv_not_json:
        lines.extend(f"- {csv_articles[key]['title']}" for key in included_by_csv_not_json)
    else:
        lines.append("- Nenhum")

    return "\n".join(lines)


def comparar_resultados(BASE_path, RESULTS_path):
    csv_articles = load_csv_articles(Path(BASE_DIR / BASE_path))
    json_results = load_json_results(Path(BASE_DIR / RESULTS_path))
    report = build_report(csv_articles, json_results)

    OUTPUT_TXT_PATH.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    comparar_resultados("source.csv", "resultados.json")
