import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_TITLE_COLUMN = "Title"
DEFAULT_ABSTRACT_COLUMN = "Abstract"
DEFAULT_SELECTED_COLUMN = "Selected"
CRITERIA_KEY = "Criteria"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_selected(value: Any) -> int:
    normalized = normalize_text(value).lower()
    selected_values = {
        "1",
        "yes",
        "y",
        "sim",
        "true",
        "in",
        "include",
        "included",
        "inclusion",
    }

    if normalized in selected_values:
        return 1
    return 0


def read_csv_rows(csv_path: str | Path) -> tuple[list[dict[str, str]], list[str]]:
    path = Path(csv_path)

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader), reader.fieldnames or []


def read_criteria(criteria_path: str | Path) -> dict[str, Any]:
    path = Path(criteria_path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if CRITERIA_KEY not in data:
        raise ValueError(f"Chave obrigatoria nao encontrada no JSON: {CRITERIA_KEY}")

    return data[CRITERIA_KEY]


def validate_required_columns(
    available_columns: list[str],
    required_columns: list[str],
) -> None:
    available_column_set = set(available_columns)
    missing_columns = [
        column for column in required_columns
        if column not in available_column_set
    ]

    if missing_columns:
        raise ValueError(
            "Colunas obrigatorias nao encontradas: "
            f"{', '.join(missing_columns)}. "
            f"Colunas disponiveis: {', '.join(sorted(available_columns))}"
        )


def row_to_result(
    row: dict[str, str],
    title_column: str = DEFAULT_TITLE_COLUMN,
    selected_column: str = DEFAULT_SELECTED_COLUMN,
) -> dict[str, str | int]:
    return {
        "title": normalize_text(row.get(title_column)),
        "selected": normalize_selected(row.get(selected_column)),
    }


def row_to_article(
    row: dict[str, str],
    title_column: str = DEFAULT_TITLE_COLUMN,
    abstract_column: str = DEFAULT_ABSTRACT_COLUMN,
) -> dict[str, str]:
    return {
        "title": normalize_text(row.get(title_column)),
        "abstract": normalize_text(row.get(abstract_column)),
    }


def build_results_payload(
    rows: list[dict[str, str]],
    columns: list[str],
    title_column: str = DEFAULT_TITLE_COLUMN,
    selected_column: str = DEFAULT_SELECTED_COLUMN,
) -> dict[str, list[dict[str, str | int]]]:
    validate_required_columns(
        columns,
        [title_column, selected_column],
    )

    results = [
        row_to_result(row, title_column, selected_column)
        for row in rows
    ]

    return {"results": results}


def build_database_payload(
    rows: list[dict[str, str]],
    columns: list[str],
    criteria: dict[str, Any],
    title_column: str = DEFAULT_TITLE_COLUMN,
    abstract_column: str = DEFAULT_ABSTRACT_COLUMN,
) -> dict[str, Any]:
    validate_required_columns(
        columns,
        [title_column, abstract_column],
    )

    articles = [
        row_to_article(row, title_column, abstract_column)
        for row in rows
    ]

    return {
        CRITERIA_KEY: criteria,
        "articles": articles,
    }


def build_articles_payload(
    rows: list[dict[str, str]],
    columns: list[str],
    title_column: str = DEFAULT_TITLE_COLUMN,
    abstract_column: str = DEFAULT_ABSTRACT_COLUMN,
    selected_column: str = DEFAULT_SELECTED_COLUMN,
) -> dict[str, list[dict[str, str | int]]]:
    validate_required_columns(
        columns,
        [title_column, abstract_column, selected_column],
    )

    articles = [
        {
            **row_to_article(row, title_column, abstract_column),
            "selected": normalize_selected(row.get(selected_column)),
        }
        for row in rows
    ]

    return {"articles": articles}


def write_json(payload: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def convert_csv_to_articles_json(
    csv_path: str | Path,
    output_path: str | Path,
    title_column: str = DEFAULT_TITLE_COLUMN,
    abstract_column: str = DEFAULT_ABSTRACT_COLUMN,
    selected_column: str = DEFAULT_SELECTED_COLUMN,
) -> dict[str, list[dict[str, str | int]]]:
    rows, columns = read_csv_rows(csv_path)
    payload = build_articles_payload(
        rows,
        columns,
        title_column=title_column,
        abstract_column=abstract_column,
        selected_column=selected_column,
    )
    write_json(payload, output_path)
    return payload


def convert_source_to_json_files(
    csv_path: str | Path,
    criteria_path: str | Path,
    results_output_path: str | Path,
    database_output_path: str | Path,
    title_column: str = DEFAULT_TITLE_COLUMN,
    abstract_column: str = DEFAULT_ABSTRACT_COLUMN,
    selected_column: str = DEFAULT_SELECTED_COLUMN,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows, columns = read_csv_rows(csv_path)
    criteria = read_criteria(criteria_path)

    results_payload = build_results_payload(
        rows,
        columns,
        title_column=title_column,
        selected_column=selected_column,
    )
    database_payload = build_database_payload(
        rows,
        columns,
        criteria,
        title_column=title_column,
        abstract_column=abstract_column,
    )

    write_json(results_payload, results_output_path)
    write_json(database_payload, database_output_path)

    return results_payload, database_payload


if __name__ == "__main__":
    convert_source_to_json_files(
        csv_path="data/study2/source2.csv",
        criteria_path="data/study2/criteria.json",
        results_output_path="data/study2/results.json",
        database_output_path="data/study2/articles.json",
    )
