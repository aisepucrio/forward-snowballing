import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Prompt, schema, leitura da resposta e regra de selecao vem do mesmo modulo da
# aplicacao (Framework_snowballing/scripts/services/prompt.py), para que o
# estudo avalie exatamente o prompt que roda na ferramenta.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "Framework_snowballing" / "scripts"))

from services.prompt import (  # noqa: E402
    CRITERIA_KEY,
    extract_criteria,
    generate_messages,
    is_selected,
    parse_criteria_response,
)


MODEL_NAME = "gemini-3.1-flash-lite-preview"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
DEFAULT_REQUEST_DELAY_SECONDS = 5
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    f"models/{MODEL_NAME}:generateContent"
)

LLMS_ANALYSIS_DIR = Path(__file__).resolve().parents[1]

ARTICLES_KEY = "articles"
RESULTS_KEY = "results"
TITLE_KEY = "title"
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

    if ARTICLES_KEY not in data or not isinstance(data[ARTICLES_KEY], list):
        raise ValueError(f"Chave obrigatoria deve ser uma lista: {ARTICLES_KEY}")

    return data


def load_criteria(
    articles_data: dict[str, Any],
    criteria_json_path: str | Path | None = None,
) -> dict[str, dict[str, str]]:
    # Os estudos guardam os criterios em criteria.json; articles.json com a
    # chave Criteria continua aceito.
    if criteria_json_path is not None:
        return extract_criteria(read_json(criteria_json_path))
    if CRITERIA_KEY in articles_data:
        return extract_criteria(articles_data)
    raise ValueError(f"Criterios nao encontrados: informe criteria_json_path ou a chave {CRITERIA_KEY}")


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


def build_gemini_request(messages: list[dict[str, str]]) -> dict[str, Any]:
    system_text = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    user_text = "\n\n".join(m["content"] for m in messages if m["role"] == "user")
    generation_config: dict[str, Any] = {"temperature": 0}
    request: dict[str, Any] = {"generationConfig": generation_config}

    # Gemma via API do Gemini nao aceita systemInstruction nem modo JSON: as
    # instrucoes vao no inicio da mensagem do usuario.
    if MODEL_NAME.startswith("gemma"):
        request["contents"] = [{"role": "user", "parts": [{"text": f"{system_text}\n\n{user_text}"}]}]
    else:
        request["systemInstruction"] = {"parts": [{"text": system_text}]}
        request["contents"] = [{"role": "user", "parts": [{"text": user_text}]}]
        generation_config["responseMimeType"] = "application/json"

    return request


def call_gemini(messages: list[dict[str, str]], api_key: str, timeout_seconds: int = 120) -> str:
    request_body = json.dumps(build_gemini_request(messages)).encode("utf-8")
    request = urllib.request.Request(
        GEMINI_API_URL,
        data=request_body,
        # Chave no header, nao na URL: URLs acabam em logs e mensagens de erro.
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
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


def analyze_article(
    article: dict[str, Any],
    criteria: dict[str, dict[str, str]],
    api_key: str,
) -> dict[str, Any] | None:
    response_text = call_gemini(generate_messages(article, criteria), api_key)
    results = parse_criteria_response(response_text, criteria)
    selected = is_selected(criteria, results)

    if selected is None:
        return None

    return {
        TITLE_KEY: str(article.get(TITLE_KEY, "")).strip(),
        SELECTED_KEY: int(selected),
        RESULTS_KEY: results,
    }


def analyze_articles_json(
    articles_json_path: str | Path,
    results_json_path: str | Path,
    criteria_json_path: str | Path | None = None,
    env_path: str | Path = ".env",
    delay_seconds: float = DEFAULT_REQUEST_DELAY_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    articles_data = load_articles_data(articles_json_path)
    criteria = load_criteria(articles_data, criteria_json_path)
    results_data = load_results_data(results_json_path)
    analyzed_titles = get_analyzed_titles(results_data)
    api_key = get_gemini_api_key(env_path)

    for article in articles_data[ARTICLES_KEY]:
        title = str(article.get(TITLE_KEY, "")).strip()

        if not title:
            continue

        if title in analyzed_titles:
            print(f"artigo {title} foi avaliado")
            continue

        try:
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            result = analyze_article(article, criteria, api_key)
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
    study_dir = LLMS_ANALYSIS_DIR / "study1"
    analyze_articles_json(
        articles_json_path=study_dir / "start_data" / "articles.json",
        criteria_json_path=study_dir / "start_data" / "criteria.json",
        results_json_path=study_dir / "gemini" / "results_llm.json",
        env_path=LLMS_ANALYSIS_DIR / ".env",
    )
