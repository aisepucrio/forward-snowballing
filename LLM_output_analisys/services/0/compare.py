import json
import re
import unicodedata
from pathlib import Path


def normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def decision_to_bool(value: str) -> bool:
    normalized = normalize_text(value)
    return normalized in {"inclusion", "include", "included", "yes", "true", "1"}


def is_countable_decision(value: str) -> bool:
    normalized = normalize_text(value)
    return normalized in {
        "inclusion", "include", "included", "yes", "true", "1",
        "exclusion", "exclude", "excluded", "no", "false", "0",
    }


def carregar_json(path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def classify_criterion_value(value: str) -> str:
    normalized = normalize_text(value)
    if normalized in {"yes", "sim", "true", "1"}:
        return "yes"
    if normalized in {"no", "nao", "não", "false", "0"}:
        return "no"
    return "not_conclusive"


def count_criteria_distribution(data):
    counts = {}

    for item in data:
        results = item.get("results", {})
        if not isinstance(results, dict):
            continue

        for criterion, value in results.items():
            criterion_name = str(criterion or "").strip().upper()
            if not re.fullmatch(r"(IC|EC)\d+", criterion_name):
                continue

            if criterion_name not in counts:
                counts[criterion_name] = {
                    "yes": 0,
                    "no": 0,
                    "not_conclusive": 0,
                    "total": 0,
                }

            bucket = classify_criterion_value(value)
            counts[criterion_name][bucket] += 1
            counts[criterion_name]["total"] += 1

    return dict(sorted(
        counts.items(),
        key=lambda item: (
            0 if item[0].startswith("IC") else 1,
            int(re.search(r"\d+", item[0]).group()),
        ),
    ))


def build_criteria_distribution_lines(source_data, llm_data):
    source_counts = count_criteria_distribution(source_data)
    llm_counts = count_criteria_distribution(llm_data)

    all_criteria = sorted(
        set(source_counts.keys()) | set(llm_counts.keys()),
        key=lambda item: (
            0 if item.startswith("IC") else 1,
            int(re.search(r"\d+", item).group()),
        ),
    )

    lines = ["", "Distribuicao por criterio:"]

    if not all_criteria:
        lines.append("- Nenhum criterio encontrado")
        return lines

    for criterion in all_criteria:
        llm_values = llm_counts.get(criterion, {"yes": 0, "no": 0, "not_conclusive": 0, "total": 0})
        source_values = source_counts.get(criterion, {"yes": 0, "no": 0, "not_conclusive": 0, "total": 0})

        llm_total = llm_values["total"]
        source_total = source_values["total"]

        llm_yes_pct = (llm_values["yes"] / llm_total * 100) if llm_total else 0.0
        llm_no_pct = (llm_values["no"] / llm_total * 100) if llm_total else 0.0
        llm_not_conclusive_pct = (llm_values["not_conclusive"] / llm_total * 100) if llm_total else 0.0

        source_yes_pct = (source_values["yes"] / source_total * 100) if source_total else 0.0
        source_no_pct = (source_values["no"] / source_total * 100) if source_total else 0.0
        source_not_conclusive_pct = (source_values["not_conclusive"] / source_total * 100) if source_total else 0.0

        lines.append(
            f"LLM > {criterion}:    Yes {llm_yes_pct:05.2f}% | No {llm_no_pct:05.2f}% | Not conclusive {llm_not_conclusive_pct:05.2f}%"
        )
        lines.append(
            f"Source > {criterion}: Yes {source_yes_pct:05.2f}% | No {source_no_pct:05.2f}% | Not conclusive {source_not_conclusive_pct:05.2f}%"
        )

    return lines


def indexar_por_titulo(data):
    indexed = {}

    for item in data:
        title = (item.get("title") or "").strip()
        if not title:
            continue

        key = normalize_text(title)
        decision = item.get("Decision", {}).get("decision", "")

        indexed[key] = {
            "title": title,
            "included": decision_to_bool(decision),
            "countable_decision": is_countable_decision(decision),
        }

    return indexed


def comparar_jsons(gabarito_path, llm_path, output_txt_path):
    gabarito_data = carregar_json(gabarito_path)
    llm_data = carregar_json(llm_path)
    gabarito = indexar_por_titulo(gabarito_data)
    llm = indexar_por_titulo(llm_data)

    ignored_keys = {
        key for key, value in llm.items()
        if not value.get("countable_decision", False)
    }

    all_keys = sorted(
        (set(gabarito.keys()) | set(llm.keys())) - ignored_keys
    )

    tp = fp = tn = fn = 0

    incluidos_llm_nao_gabarito = []
    incluidos_gabarito_nao_llm = []

    for key in all_keys:
        expected = gabarito.get(key, {}).get("included", False)
        predicted = llm.get(key, {}).get("included", False)

        if expected and predicted:
            tp += 1
        elif not expected and predicted:
            fp += 1
            title = llm.get(key, {}).get("title") or gabarito.get(key, {}).get("title") or key
            incluidos_llm_nao_gabarito.append(title)
        elif expected and not predicted:
            fn += 1
            title = gabarito.get(key, {}).get("title") or llm.get(key, {}).get("title") or key
            incluidos_gabarito_nao_llm.append(title)
        else:
            tn += 1

    total = tp + fp + tn + fn
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) else 0.0

    report_lines = [
        "Analise da comparacao entre gabarito e selecao da LLM",
        "",
        f"Artigos ignorados por decisao nao contabilizavel: {len(ignored_keys)}",
        f"Total de artigos avaliados: {total}",
        f"True Positives (TP): {tp}",
        f"False Positives (FP): {fp}",
        f"True Negatives (TN): {tn}",
        f"False Negatives (FN): {fn}",
        "",
        f"Recall: {recall:.4f}",
        f"Precision: {precision:.4f}",
        f"Acuracia: {accuracy:.4f}",
        f"F1-score: {f1_score:.4f}",
        "",
        "Artigos incluidos pela LLM e nao incluidos no gabarito:",
    ]

    if incluidos_llm_nao_gabarito:
        report_lines.extend(f"- {title}" for title in incluidos_llm_nao_gabarito)
    else:
        report_lines.append("- Nenhum")

    report_lines.extend([
        "",
        "Artigos incluidos no gabarito e nao incluidos pela LLM:",
    ])

    if incluidos_gabarito_nao_llm:
        report_lines.extend(f"- {title}" for title in incluidos_gabarito_nao_llm)
    else:
        report_lines.append("- Nenhum")

    report_lines.extend(build_criteria_distribution_lines(gabarito_data, llm_data))

    report = "\n".join(report_lines)

    output_txt_path = Path(output_txt_path)
    output_txt_path.write_text(report, encoding="utf-8")

    return report


if __name__ == "__main__":
    comparar_jsons("resultados_originais.json", "resultados.json", "comparacao.txt")
