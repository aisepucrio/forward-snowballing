import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from services.prompt import generate_prompt
except ModuleNotFoundError:
    from prompt import generate_prompt


MODEL_NAME = "gemini-3.1-flash-lite-preview" 
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
DEFAULT_REQUEST_DELAY_SECONDS = 5
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL_NAME}:generateContent"
)

CRITERIA_KEY = "Criteria"
ARTICLES_KEY = "articles"
RESULTS_KEY = "results"
TITLE_KEY = "title"
ABSTRACT_KEY = "abstract"
SELECTED_KEY = "selected"


def load_env_file(env_path: str | Path = ".env") -> None:
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def get_gemini_api_key(env_path: str | Path = ".env") -> str:
    load_env_file(env_path)
    api_key = os.getenv(GEMINI_API_KEY_ENV, "").strip()

    if not api_key:
        raise ValueError(f"Variavel de ambiente nao encontrada: {GEMINI_API_KEY_ENV}")

    return api_key


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


def build_gemini_request(prompt: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0,
        },
    }


def call_gemini(prompt: str, api_key: str, timeout_seconds: int = 120) -> str:
    request_body = json.dumps(build_gemini_request(prompt)).encode("utf-8")
    request = urllib.request.Request(
        f"{GEMINI_API_URL}?key={api_key}",
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Erro HTTP Gemini {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Erro ao conectar ao Gemini: {error}") from error

    return extract_gemini_text(data)


def extract_gemini_text(response_data: dict[str, Any]) -> str:
    candidates = response_data.get("candidates", [])
    if not candidates:
        return ""

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])

    texts = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ]

    return "\n".join(texts).strip()


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
    api_key: str,
) -> dict[str, Any] | None:
    prompt = generate_prompt(title, abstract, criteria)
    response_text = call_gemini(prompt, api_key)
    selected = parse_llm_selected(response_text)

    if selected is None:
        return None

    return build_output_result(title, selected)


def analyze_articles_json(
    articles_json_path: str | Path,
    results_json_path: str | Path,
    env_path: str | Path = ".env",
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    articles_data = load_articles_data(articles_json_path)
    results_data = load_results_data(results_json_path)
    analyzed_titles = get_analyzed_titles(results_data)
    api_key = get_gemini_api_key(env_path)

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

            result = analyze_article(title, abstract, criteria, api_key)
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


if __name__ == "__main__":
    analyze_articles_json(
        articles_json_path="data/study1/articles.json",
        results_json_path="data/study1/results_llm.json",
    )
