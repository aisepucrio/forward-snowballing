"""
Roda a triagem de um estudo pelo mesmo caminho da aplicacao: o prompt de
scripts/services/prompt.py e o cliente de
scripts/analisys_LLM.py (OpenRouter, fallback para o Gemini, novas tentativas e
leitura da resposta). O que se mede aqui e o que roda em producao.

    python code/run_screening.py study0
    python code/run_screening.py study1 --limit 20 --run sem-exemplos

Os resultados sao gravados a cada artigo em
studies/<estudo>/runs/<execucao>/results.json, entao uma execucao interrompida
continua de onde parou ao ser chamada de novo com o mesmo --run.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analisys_LLM import (  # noqa: E402
    DEFAULT_GEMINI_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    LLMFatalError,
    classificar_artigo,
)
from services.prompt import (  # noqa: E402
    ANSWER_ERROR,
    extract_criteria,
    generate_messages,
    is_selected,
)

STUDIES_DIR = Path(__file__).resolve().parents[1] / "studies"
DEFAULT_WORKERS = 4


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def study_dir(study):
    path = Path(study)
    return path if path.is_dir() else STUDIES_DIR / study


def load_study(study):
    """Artigos e criterios de um estudo. Os criterios ficam em criteria.json;
    articles.json com a chave Criteria tambem e aceito."""
    start_data = study_dir(study) / "start_data"
    articles_data = read_json(start_data / "articles.json")
    articles = articles_data.get("articles")
    if not isinstance(articles, list):
        raise SystemExit(f"articles.json sem lista 'articles': {start_data}")

    criteria_path = start_data / "criteria.json"
    criteria_source = read_json(criteria_path) if criteria_path.exists() else articles_data
    return articles, extract_criteria(criteria_source)


def coerce_int(value, default):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def prompt_fingerprint(article, criteria):
    """Identifica a versao do prompt usada na execucao, para nao comparar
    resultados de prompts diferentes sem perceber."""
    system_message = generate_messages(article, criteria)[0]["content"]
    return hashlib.sha256(system_message.encode("utf-8")).hexdigest()[:12]


def run_settings():
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    return {
        "model": os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODEL,
        "openrouter_fallbacks": os.getenv("LLM_FALLBACK_MODELS", "").strip(),
        "gemini_fallback": (os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL) if gemini_key else None,
        "structured_output": os.getenv("LLM_STRUCTURED_OUTPUT", "true"),
        "reasoning": os.getenv("LLM_REASONING", "false"),
        "temperature": os.getenv("LLM_TEMPERATURE", "0"),
        "max_tokens": os.getenv("LLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)),
    }


def default_run_name(settings):
    model = settings["model"].split("/")[-1].replace(":", "-")
    return f"{model}-{datetime.now().strftime('%Y%m%d-%H%M')}"


def load_previous(results_path):
    if not results_path.exists():
        return []
    data = read_json(results_path)
    previous = data.get("results") if isinstance(data, dict) else None
    return previous if isinstance(previous, list) else []


def save(results_path, payload):
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Triagem de um estudo pelo cliente da aplicacao.")
    parser.add_argument("study", help="study0, study1 ou o caminho de um diretorio de estudo")
    parser.add_argument("--run", help="nome da execucao (padrao: modelo + data)")
    parser.add_argument("--limit", type=int, help="analisa apenas os N primeiros artigos")
    parser.add_argument("--workers", type=int, help="chamadas em paralelo (padrao: LLM_MAX_WORKERS)")
    parser.add_argument("--fresh", action="store_true", help="ignora os resultados ja gravados nesta execucao")
    args = parser.parse_args()

    articles, criteria = load_study(args.study)
    if args.limit:
        articles = articles[: args.limit]

    settings = run_settings()
    run_name = args.run or default_run_name(settings)
    results_path = study_dir(args.study) / "runs" / run_name / "results.json"

    previous = [] if args.fresh else load_previous(results_path)
    analyzed_titles = {str(item.get("title", "")).strip() for item in previous}
    pending = [a for a in articles if str(a.get("title", "")).strip() not in analyzed_titles]

    meta = {
        "run": run_name,
        "study": str(study_dir(args.study).name),
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "prompt": prompt_fingerprint(articles[0], criteria) if articles else None,
        "articles": len(articles),
        **settings,
    }

    print(
        f"{meta['study']}: {len(articles)} artigos, {len(previous)} ja analisados, {len(pending)} pendentes",
        file=sys.stderr,
    )
    print(f"execucao: {run_name} | modelo: {settings['model']} | fallback: {settings['gemini_fallback']}", file=sys.stderr)

    results = list(previous)
    lock = threading.Lock()

    def screen(article):
        result = classificar_artigo(article, criteria)
        result["selected"] = is_selected(criteria, result["results"])
        with lock:
            results.append(result)
            save(results_path, {"run": {**meta, "analyzed": len(results)}, "results": results})
            print(f"{len(results)}/{len(articles)} {str(result['title'])[:70]}", file=sys.stderr)

    workers = args.workers or coerce_int(os.getenv("LLM_MAX_WORKERS"), DEFAULT_WORKERS)
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            list(executor.map(screen, pending))
    except LLMFatalError as error:
        print(f"[FALHA] {error}", file=sys.stderr)
        print(f"Resultados parciais em {results_path}; rode de novo com --run {run_name} para continuar", file=sys.stderr)
        return 1

    errors = sum(1 for item in results if ANSWER_ERROR in (item.get("results") or {}).values())
    save(results_path, {"run": {**meta, "analyzed": len(results), "errors": errors}, "results": results})
    print(f"pronto: {len(results)} artigos, {errors} com erro -> {results_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
