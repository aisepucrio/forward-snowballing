import json
import os
import sys

import requests

from services.prompt import (
    criteria_from_text,
    expected_criteria_ids,
    generate_prompt,
)


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://11.0.0.35:11434/api/chat")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "gemma4:31b")
MODEL_FALLBACKS = ["llama3.2:3b", "mistral:latest"]
FAILED_MODELS = set()


def _model_candidates():
    candidates = [MODEL_NAME, *MODEL_FALLBACKS]
    seen = set()
    return [
        model
        for model in candidates
        if model and model not in seen and not seen.add(model)
    ]


def _call_ollama(prompt, model=None, temperature=0.1, tokens=600, ollama_url=None):
    last_error = None
    url = ollama_url or OLLAMA_URL
    candidates = [model] + MODEL_FALLBACKS if model else _model_candidates()

    for model_name in candidates:
        if not model_name or model_name in FAILED_MODELS:
            continue

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "options": {
                "temperature": temperature,
                "num_predict": tokens
            },
            "stream": False,
            "think": False
        }

        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception as model_error:
            FAILED_MODELS.add(model_name)
            last_error = model_error
            print(f"[ERRO Ollama model={model_name}] {model_error}", file=sys.stderr)

    raise RuntimeError(f"Nenhum modelo Ollama respondeu. Ultimo erro: {last_error}")


def _extract_json_object(text):
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("JSON nao encontrado na resposta")

    return json.loads(text[start:end + 1])


def _normalize_criterion_answer(value):
    normalized = str(value or "").strip().lower()

    if normalized in {"sim", "yes"}:
        return "Yes"

    if normalized in {"nao", "não", "nÃ£o", "nÃƒÂ£o", "no", "nÃƒÆ’Ã‚Â£o"}:
        return "No"

    if normalized in {"unsure", "incerto", "talvez", "maybe"}:
        return "Unsure"

    return "error"


def _fallback_result(title, criteria):
    return {
        "title": title,
        "results": {
            criterion_id: "error"
            for criterion_id in expected_criteria_ids(criteria)
        }
    }


def classificar_artigo(article, criteria, model=None, temperature=0.1, tokens=600, ollama_url=None, extra_prompt=""):
    title = article.get("title", "")
    prompt = generate_prompt(
        article=article,
        criteria=criteria,
        extra_prompt=extra_prompt,
    )

    try:
        data = _extract_json_object(_call_ollama(prompt, model=model, temperature=temperature, tokens=tokens, ollama_url=ollama_url))
        raw_criteria = data.get("criteria") if isinstance(data.get("criteria"), dict) else {}

        if not raw_criteria:
            raise ValueError("Resposta da LLM sem objeto 'criteria' valido")

        return {
            "title": title,
            "results": {
                criterion_id: _normalize_criterion_answer(raw_criteria.get(criterion_id))
                for criterion_id in expected_criteria_ids(criteria)
            }
        }

    except Exception as e:
        print(f"[ERRO Ollama] {e}", file=sys.stderr)
        return _fallback_result(title, criteria)


def analisar(criterios_inclusao, criterios_exclusao, artigos, model=None, temperature=0.1, tokens=600, ollama_url=None, extra_prompt=""):
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    results = []

    for artigo in artigos:
        results.append(classificar_artigo(artigo, criteria, model=model, temperature=temperature, tokens=tokens, ollama_url=ollama_url, extra_prompt=extra_prompt))

    return results


if __name__ == "__main__":
    input_json = sys.stdin.read()
    data = json.loads(input_json)

    criterios_inclusao = data.get("criteriosInclusao", "")
    criterios_exclusao = data.get("criteriosExclusao", "")
    artigos = data.get("artigos", [])
    model = data.get("model", MODEL_NAME)
    temperature = data.get("temperature", 0.1)
    tokens = data.get("tokens", 600)
    ollama_url = data.get("ollamaUrl", OLLAMA_URL)
    extra_prompt = data.get("extraPrompt", "")

    results = analisar(criterios_inclusao, criterios_exclusao, artigos, model, temperature, tokens, ollama_url, extra_prompt)

    print(json.dumps(results, ensure_ascii=False))
