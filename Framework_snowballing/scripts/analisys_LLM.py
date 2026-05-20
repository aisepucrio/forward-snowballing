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


def _call_ollama(prompt):
    last_error = None

    for model_name in _model_candidates():
        if model_name in FAILED_MODELS:
            continue

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "options": {
                "temperature": 0.1,
                "num_predict": 600
            },
            "stream": False,
            "think": False
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
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

    if normalized in {"nao", "não", "nÃ£o", "no", "nÃƒÂ£o"}:
        return "No"

    return "No"


def _fallback_result(title, criteria):
    return {
        "title": title,
        "results": {
            criterion_id: "error"
            for criterion_id in expected_criteria_ids(criteria)
        }
    }


def classificar_artigo(title, summary, criteria):
    prompt = generate_prompt(
        title=title,
        abstract=summary,
        criteria=criteria,
    )

    try:
        data = _extract_json_object(_call_ollama(prompt))
        raw_criteria = data.get("criteria") if isinstance(data.get("criteria"), dict) else {}

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


def analisar(criterios_inclusao, criterios_exclusao, artigos):
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    results = []

    for artigo in artigos:
        title = artigo.get("title", "")
        abstract = artigo.get("abstract", "")

        results.append(classificar_artigo(title, abstract, criteria))

    return results


if __name__ == "__main__":
    input_json = sys.stdin.read()
    data = json.loads(input_json)

    criterios_inclusao = data.get("criteriosInclusao", "")
    criterios_exclusao = data.get("criteriosExclusao", "")
    artigos = data.get("artigos", [])

    results = analisar(criterios_inclusao, criterios_exclusao, artigos)

    print(json.dumps(results, ensure_ascii=False))
