import csv
import json
from pathlib import Path


def csv_selected_to_decision(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"yes", "sim", "true", "1", "inclusion", "include", "included"}:
        return "inclusion"
    return "exclusion"


def normalize_criterion_value(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"yes", "sim", "true", "1"}:
        return "Yes"
    if normalized in {"no", "nao", "não", "false", "0"}:
        return "No"
    return str(value or "").strip()


def converter_csv_para_json(csv_path, output_path):
    csv_path = Path(csv_path)
    output_path = Path(output_path)

    resultados = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            title = (row.get("Title") or "").strip()
            if not title:
                continue

            results = {}
            for column_name, value in row.items():
                if not column_name:
                    continue

                col = column_name.strip()
                col_lower = col.lower()

                if col_lower.startswith("ic") and col[2:].isdigit():
                    results[col.upper()] = normalize_criterion_value(value)
                elif col_lower.startswith("ec") and col[2:].isdigit():
                    results[col.upper()] = normalize_criterion_value(value)

            resultados.append({
                "title": title,
                "results": results,
                "Decision": {
                    "decision": csv_selected_to_decision(row.get("Selected", "")),
                    "confidence": 1
                }
            })

    output_path.write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return resultados


if __name__ == "__main__":
    converter_csv_para_json("source.csv", "resultados_originais.json")