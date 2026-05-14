import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from services.prompt import generate_prompt
except ModuleNotFoundError:
    from prompt import generate_prompt


MODEL_NAME = "gemma4:31b"
OLLAMA_BASE_URL = "http://11.0.0.35:11434"
DEFAULT_REQUEST_DELAY_SECONDS = 5

CRITERIA_KEY = "Criteria"
ARTICLES_KEY = "articles"
RESULTS_KEY = "results"
TITLE_KEY = "title"
ABSTRACT_KEY = "abstract"
SELECTED_KEY = "selected"


def read_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    if not json_path.exists():
        return {}

    text = json_path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return {}

    return json.loads(text)


def write_json(payload: dict[str, Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_articles_data(articles_json_path: str | Path) -> dict[str, Any]:
    data = read_json(articles_json_path)

    if CRITERIA_KEY not in data:
        raise ValueError(f"Chave obrigatoria nao encontrada: {CRITERIA_KEY}")

    if ARTICLES_KEY not in data or not isinstance(data[ARTICLES_KEY], list):
        raise ValueError(f"Chave obrigatoria deve ser uma lista: {ARTICLES_KEY}")

    return data


def load_results_data(results_json_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    data = read_json(results_json_path)
    results = data.get(RESULTS_KEY, [])

    if not isinstance(results, list):
        raise ValueError(f"Chave obrigatoria deve ser uma lista: {RESULTS_KEY}")

    return {RESULTS_KEY: results}


def get_analyzed_titles(results_data: dict[str, list[dict[str, Any]]]) -> set[str]:
    return {
        str(item.get(TITLE_KEY, "")).strip()
        for item in results_data[RESULTS_KEY]
        if str(item.get(TITLE_KEY, "")).strip()
    }


def build_ollama_request(prompt: str, model_name: str = MODEL_NAME) -> dict[str, Any]:
    return {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 128,
        },
    }


def normalize_ollama_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def call_ollama(
    prompt: str,
    base_url: str = OLLAMA_BASE_URL,
    model_name: str = MODEL_NAME,
    timeout_seconds: int = 600,
) -> str:
    request_body = json.dumps(build_ollama_request(prompt, model_name)).encode("utf-8")
    url = f"{normalize_ollama_base_url(base_url)}/api/generate"
    request = urllib.request.Request(
        url,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Erro HTTP Ollama {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Erro ao conectar ao Ollama: {error}") from error

    return str(data.get("response", "")).strip()


def strip_json_markdown(text: str) -> str:
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    return cleaned


def parse_llm_selected(text: str) -> int | None:
    cleaned = strip_json_markdown(text).strip()

    if cleaned in {"0", "1"}:
        return int(cleaned)

    match = re.search(r"(?<!\d)[01](?!\d)", cleaned)
    if match:
        return int(match.group(0))

    return None


def build_output_result(article_title: str, selected: int) -> dict[str, Any]:
    return {
        TITLE_KEY: article_title,
        SELECTED_KEY: selected,
    }


def analyze_article(
    title: str,
    abstract: str,
    criteria: dict[str, Any],
    base_url: str = OLLAMA_BASE_URL,
    model_name: str = MODEL_NAME,
) -> dict[str, Any] | None:
    prompt = generate_prompt(title, abstract, criteria)
    response_text = call_ollama(prompt, base_url=base_url, model_name=model_name)
    selected = parse_llm_selected(response_text)

    if selected is None:
        return None

    return build_output_result(title, selected)


def analyze_articles_json(
    articles_json_path: str | Path,
    results_json_path: str | Path,
    base_url: str = OLLAMA_BASE_URL,
    model_name: str = MODEL_NAME,
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    articles_data = load_articles_data(articles_json_path)
    results_data = load_results_data(results_json_path)
    analyzed_titles = get_analyzed_titles(results_data)

    criteria = articles_data[CRITERIA_KEY]
    articles = articles_data[ARTICLES_KEY]

    for article in articles:
        title = str(article.get(TITLE_KEY, "")).strip()
        abstract = str(article.get(ABSTRACT_KEY, "")).strip()

        if not title:
            continue

        if title in analyzed_titles:
            print(f"artigo {title} foi avaliado")
            continue

        try:
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            result = analyze_article(
                title,
                abstract,
                criteria,
                base_url=base_url,
                model_name=model_name,
            )
        except Exception as error:
            print(f"erro {error}")
            continue

        if result is None:
            print("erro resposta invalida da LLM")
            continue

        results_data[RESULTS_KEY].append(result)
        analyzed_titles.add(title)
        write_json(results_data, results_json_path)
        print(f"artigo {title} classificado")

    return results_data


def test_ollama_connection(
    base_url: str = OLLAMA_BASE_URL,
    model_name: str = MODEL_NAME,
) -> str:
    return call_ollama(
        "Return only the number 1.",
        base_url=base_url,
        model_name=model_name,
        timeout_seconds=120,
    )


if __name__ == "__main__":
    analyze_articles_json(
        articles_json_path="data/study2/articles.json",
        results_json_path="data/study2/results_local.json",
        base_url=OLLAMA_BASE_URL,
        model_name=MODEL_NAME,
    )
