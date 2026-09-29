"""
Compara uma execucao de run_screening.py com o gabarito humano do estudo.

    python code/compare.py study0
    python code/compare.py study1 --run nemotron-3-ultra-550b-a55b-free-20260929-1200

Mede a decisao final (incluir/excluir) e, quando o gabarito traz veredito por
criterio (caso do study0), tambem a concordancia criterio a criterio. O
relatorio vai para o diretorio da execucao e para a tela.
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "Framework_snowballing" / "scripts"))

from services.prompt import (  # noqa: E402
    ANSWER_ERROR,
    EXCLUSION_KEY,
    INCLUSION_KEY,
    expected_criteria_ids,
    extract_criteria,
    is_selected,
)

STUDIES_DIR = Path(__file__).resolve().parents[1] / "studies"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def study_dir(study):
    path = Path(study)
    return path if path.is_dir() else STUDIES_DIR / study


def load_criteria(study_path):
    start_data = study_path / "start_data"
    criteria_path = start_data / "criteria.json"
    source = read_json(criteria_path) if criteria_path.exists() else read_json(start_data / "articles.json")
    return extract_criteria(source)


def normalize_selected(value):
    normalized = str(value).strip().lower()
    if normalized in {"1", "yes", "y", "sim", "true", "inclusion", "include", "included"}:
        return 1
    if normalized in {"0", "no", "n", "nao", "false", "exclusion", "exclude", "excluded"}:
        return 0
    return None


def item_verdict(item, criteria):
    """Le um item de gabarito ou de execucao nos formatos que existem no
    repositorio: {"selected": 0|1}, {"Decision": {"decision": ...}} ou
    {"results": {"IC1": "Yes", ...}}."""
    answers = item.get("results") if isinstance(item.get("results"), dict) else None

    selected = None
    if "selected" in item:
        selected = normalize_selected(item.get("selected"))
    if selected is None and isinstance(item.get("Decision"), dict):
        selected = normalize_selected(item["Decision"].get("decision"))
    if selected is None and answers:
        decided = is_selected(criteria, answers)
        selected = None if decided is None else int(decided)

    return {"selected": selected, "criteria": answers}


def load_verdicts(path, criteria):
    data = read_json(path)
    items = data if isinstance(data, list) else data.get("results", [])

    verdicts = {}
    duplicates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        if title in verdicts:
            duplicates.append(title)
        verdicts[title] = item_verdict(item, criteria)

    return verdicts, duplicates


def latest_run(study_path):
    runs = [d for d in (study_path / "runs").glob("*") if (d / "results.json").exists()]
    if not runs:
        raise SystemExit(f"Nenhuma execucao em {study_path / 'runs'}. Rode code/run_screening.py primeiro.")
    return max(runs, key=lambda d: (d / "results.json").stat().st_mtime)


def divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def decision_metrics(gold, run):
    compared = [t for t in gold if t in run and gold[t]["selected"] is not None and run[t]["selected"] is not None]

    true_positives = [t for t in compared if gold[t]["selected"] == 1 and run[t]["selected"] == 1]
    false_positives = [t for t in compared if gold[t]["selected"] == 0 and run[t]["selected"] == 1]
    false_negatives = [t for t in compared if gold[t]["selected"] == 1 and run[t]["selected"] == 0]
    true_negatives = [t for t in compared if gold[t]["selected"] == 0 and run[t]["selected"] == 0]

    precision = divide(len(true_positives), len(true_positives) + len(false_positives))
    recall = divide(len(true_positives), len(true_positives) + len(false_negatives))

    return {
        "compared": compared,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "precision": precision,
        "recall": recall,
        "f1": divide(2 * precision * recall, precision + recall),
        "accuracy": divide(len(true_positives) + len(true_negatives), len(compared)),
        "missing_in_run": sorted(t for t in gold if t not in run),
        "extra_in_run": sorted(t for t in run if t not in gold),
    }


def criteria_metrics(gold, run, criteria):
    """Concordancia por criterio, so para os artigos em que os dois lados tem
    veredito criterio a criterio."""
    per_criterion = {}
    for criterion_id in expected_criteria_ids(criteria):
        agree = disagree = 0
        for title, gold_item in gold.items():
            run_item = run.get(title)
            if not run_item or not gold_item["criteria"] or not run_item["criteria"]:
                continue
            expected = gold_item["criteria"].get(criterion_id)
            answered = run_item["criteria"].get(criterion_id)
            if expected is None or answered in (None, ANSWER_ERROR):
                continue
            if str(expected).strip().lower() == str(answered).strip().lower():
                agree += 1
            else:
                disagree += 1
        if agree or disagree:
            per_criterion[criterion_id] = {
                "agree": agree,
                "disagree": disagree,
                "agreement": divide(agree, agree + disagree),
            }
    return per_criterion


def percent(value):
    return f"{value * 100:.2f}%"


def title_list(titles, limit=20):
    if not titles:
        return "- nenhum"
    shown = [f"- {title}" for title in titles[:limit]]
    if len(titles) > limit:
        shown.append(f"- ... e mais {len(titles) - limit}")
    return "\n".join(shown)


def build_report(study, run_meta, gold, run, metrics, per_criterion, errors, duplicates):
    lines = [
        f"Comparacao com o gabarito - {study}",
        "",
        "Execucao",
        f"- run: {run_meta.get('run')}",
        f"- modelo: {run_meta.get('model')}",
        f"- fallback Gemini: {run_meta.get('gemini_fallback')}",
        f"- prompt: {run_meta.get('prompt')}",
        f"- raciocinio: {run_meta.get('reasoning')} | json schema: {run_meta.get('structured_output')}"
        f" | temperatura: {run_meta.get('temperature')}",
        "",
        "Resumo",
        f"- artigos no gabarito: {len(gold)}",
        f"- artigos na execucao: {len(run)}",
        f"- artigos comparados: {len(metrics['compared'])}",
        f"- artigos com erro na execucao: {errors}",
        "",
        "Decisao final (gabarito como referencia)",
        f"- precision: {metrics['precision']:.4f}",
        f"- recall: {metrics['recall']:.4f}",
        f"- f1: {metrics['f1']:.4f}",
        f"- accuracy: {metrics['accuracy']:.4f}",
        "",
        "Matriz",
        f"- true positives: {len(metrics['true_positives'])}",
        f"- false positives: {len(metrics['false_positives'])}",
        f"- false negatives: {len(metrics['false_negatives'])}",
        f"- true negatives: {len(metrics['true_negatives'])}",
    ]

    if per_criterion:
        lines += ["", "Concordancia por criterio"]
        for criterion_id, data in per_criterion.items():
            lines.append(
                f"- {criterion_id}: {percent(data['agreement'])}"
                f" ({data['agree']} iguais, {data['disagree']} diferentes)"
            )

    lines += [
        "",
        "Incluidos pela LLM e excluidos no gabarito (falsos positivos)",
        title_list(sorted(metrics["false_positives"])),
        "",
        "Excluidos pela LLM e incluidos no gabarito (falsos negativos)",
        title_list(sorted(metrics["false_negatives"])),
        "",
        "Artigos do gabarito sem resultado na execucao",
        title_list(metrics["missing_in_run"]),
        "",
        "Artigos da execucao ausentes no gabarito",
        title_list(metrics["extra_in_run"]),
    ]

    if duplicates:
        lines += ["", "Titulos duplicados", title_list(sorted(set(duplicates)))]

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Compara uma execucao com o gabarito do estudo.")
    parser.add_argument("study", help="study0, study1 ou o caminho de um diretorio de estudo")
    parser.add_argument("--run", help="nome da execucao (padrao: a mais recente)")
    parser.add_argument("--gold", help="caminho do gabarito (padrao: start_data/ground_truth.json)")
    args = parser.parse_args()

    study_path = study_dir(args.study)
    criteria = load_criteria(study_path)

    run_path = (study_path / "runs" / args.run) if args.run else latest_run(study_path)
    results_file = run_path / "results.json"
    if not results_file.exists():
        raise SystemExit(f"Execucao sem results.json: {run_path}")

    gold_path = Path(args.gold) if args.gold else study_path / "start_data" / "ground_truth.json"
    gold, gold_duplicates = load_verdicts(gold_path, criteria)
    run, run_duplicates = load_verdicts(results_file, criteria)
    run_meta = read_json(results_file).get("run", {})

    errors = sum(
        1
        for item in read_json(results_file).get("results", [])
        if ANSWER_ERROR in (item.get("results") or {}).values()
    )

    metrics = decision_metrics(gold, run)
    per_criterion = criteria_metrics(gold, run, criteria)
    report = build_report(
        study_path.name, run_meta, gold, run, metrics, per_criterion, errors, gold_duplicates + run_duplicates
    )

    report_path = run_path / "comparison.txt"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"relatorio: {report_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
