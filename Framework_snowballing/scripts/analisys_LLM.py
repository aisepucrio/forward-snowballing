import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from services.prompt import (
    criteria_from_text,
    expected_criteria_ids,
    generate_batch_prompt,
    generate_prompt,
)


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://11.0.0.35:11434/api/chat")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
MODEL_FALLBACKS = ["mistral:latest", "gemma4:31b"]
FAILED_MODELS = set()
DEFAULT_LLM_WORKERS = 4
DEFAULT_BATCH_SIZE = 5


def _model_candidates():
    candidates = [MODEL_NAME, *MODEL_FALLBACKS]
    seen = set()
    return [
        model
        for model in candidates
        if model and model not in seen and not seen.add(model)
    ]


def _call_ollama(prompt, model=None, temperature=0.1, tokens=600, ollama_url=None, max_predict=900, timeout=120):
    last_error = None
    url = ollama_url or OLLAMA_URL
    explicit_model = bool(model)
    if explicit_model:
        candidates = [model, *[m for m in MODEL_FALLBACKS if m and m != model]]
    else:
        candidates = _model_candidates()

    for model_name in candidates:
        if not model_name or (not explicit_model and model_name in FAILED_MODELS):
            continue

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "options": {
                "temperature": temperature,
                "num_predict": min(_coerce_positive_int(tokens, 180), max_predict)
            },
            "format": "json",
            "stream": False,
            "think": False
        }

        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except Exception as model_error:
            if not explicit_model:
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


def _extract_json_value(text):
    cleaned = text.strip()
    candidates = [
        (cleaned.find("{"), cleaned.rfind("}")),
        (cleaned.find("["), cleaned.rfind("]")),
    ]
    candidates = [
        (start, end)
        for start, end in candidates
        if start != -1 and end != -1 and end > start
    ]

    if not candidates:
        raise ValueError("JSON nao encontrado na resposta")

    start, end = min(candidates, key=lambda item: item[0])
    return json.loads(cleaned[start:end + 1])


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
            criterion_id: "Unsure"
            for criterion_id in expected_criteria_ids(criteria)
        }
    }


def _coerce_positive_int(value, default):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def classificar_artigo(article, criteria, model=None, temperature=0.1, tokens=600, ollama_url=None, extra_prompt=""):
    title = article.get("title", "")
    prompt = generate_prompt(
        article=article,
        criteria=criteria,
        extra_prompt=extra_prompt,
    )

    try:
        data = _extract_json_object(_call_ollama(prompt, model=model, temperature=temperature, tokens=tokens, ollama_url=ollama_url, max_predict=400, timeout=60))
        raw_criteria = data.get("criteria") if isinstance(data.get("criteria"), dict) else {}
        if not raw_criteria and isinstance(data, dict):
            expected_ids = set(expected_criteria_ids(criteria))
            raw_criteria = {
                criterion_id: data.get(criterion_id)
                for criterion_id in expected_ids
                if criterion_id in data
            }

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


def _normalize_result_from_raw(article, raw_result, criteria):
    raw_criteria = {}

    if isinstance(raw_result, dict):
        raw_criteria = raw_result.get("criteria") if isinstance(raw_result.get("criteria"), dict) else {}

        if not raw_criteria:
            expected_ids = set(expected_criteria_ids(criteria))
            raw_criteria = {
                criterion_id: raw_result.get(criterion_id)
                for criterion_id in expected_ids
                if criterion_id in raw_result
            }

    if not raw_criteria:
        return _fallback_result(article.get("title", ""), criteria)

    return {
        "title": article.get("title", ""),
        "results": {
            criterion_id: _normalize_criterion_answer(raw_criteria.get(criterion_id))
            for criterion_id in expected_criteria_ids(criteria)
        }
    }


def classificar_lote(articles, criteria, model=None, temperature=0.1, tokens=600, ollama_url=None, extra_prompt=""):
    if not articles:
        return []

    prompt = generate_batch_prompt(
        articles=articles,
        criteria=criteria,
        extra_prompt=extra_prompt,
    )

    try:
        requested_tokens = max(
            _coerce_positive_int(tokens, 300),
            120 + len(articles) * max(len(expected_criteria_ids(criteria)), 1) * 35,
        )
        data = _extract_json_value(
            _call_ollama(
                prompt,
                model=model,
                temperature=temperature,
                tokens=requested_tokens,
                ollama_url=ollama_url,
                max_predict=1200,
                timeout=120,
            )
        )

        raw_items = data.get("articles") if isinstance(data, dict) else data
        if not isinstance(raw_items, list):
            raise ValueError("Resposta batch sem lista de artigos")

        by_index = {}
        for position, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                continue
            raw_index = raw_item.get("index", position)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = position
            by_index[index] = raw_item

        return [
            _normalize_result_from_raw(article, by_index.get(index, {}), criteria)
            for index, article in enumerate(articles)
        ]

    except Exception as e:
        print(f"[ERRO Ollama batch] {e}", file=sys.stderr)
        return [
            classificar_artigo(
                article,
                criteria,
                model=model,
                temperature=temperature,
                tokens=tokens,
                ollama_url=ollama_url,
                extra_prompt=extra_prompt,
            )
            for article in articles
        ]


def _chunked(items, size):
    size = max(1, size)
    for index in range(0, len(items), size):
        yield items[index:index + size]


def analisar(criterios_inclusao, criterios_exclusao, artigos, model=None, temperature=0.1, tokens=600, ollama_url=None, extra_prompt="", max_workers=None):
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    batch_size = _coerce_positive_int(os.getenv("LLM_BATCH_SIZE"), DEFAULT_BATCH_SIZE)
    batches = list(_chunked(artigos, batch_size))
    worker_count = min(
        _coerce_positive_int(max_workers or os.getenv("LLM_MAX_WORKERS"), DEFAULT_LLM_WORKERS),
        max(len(batches), 1),
    )

    if worker_count <= 1:
        results = []
        for batch in batches:
            results.extend(
                classificar_lote(
                    batch,
                    criteria,
                    model=model,
                    temperature=temperature,
                    tokens=tokens,
                    ollama_url=ollama_url,
                    extra_prompt=extra_prompt,
                )
            )
        return results

    results = [None] * len(batches)

    def _classify_batch(index, batch):
        return index, classificar_lote(
            batch,
            criteria,
            model=model,
            temperature=temperature,
            tokens=tokens,
            ollama_url=ollama_url,
            extra_prompt=extra_prompt,
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_classify_batch, index, batch)
            for index, batch in enumerate(batches)
        ]

        for future in as_completed(futures):
            index, batch_result = future.result()
            results[index] = batch_result

    flattened = []
    for batch_result in results:
        flattened.extend(batch_result or [])

    return flattened


def analisar_individual(criterios_inclusao, criterios_exclusao, artigos, model=None, temperature=0.1, tokens=600, ollama_url=None, extra_prompt="", max_workers=None):
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    worker_count = min(
        _coerce_positive_int(max_workers or os.getenv("LLM_MAX_WORKERS"), DEFAULT_LLM_WORKERS),
        max(len(artigos), 1),
    )

    if worker_count <= 1:
        return [
            classificar_artigo(
                artigo,
                criteria,
                model=model,
                temperature=temperature,
                tokens=tokens,
                ollama_url=ollama_url,
                extra_prompt=extra_prompt,
            )
            for artigo in artigos
        ]

    results = [None] * len(artigos)

    def _classify(index, artigo):
        return index, classificar_artigo(
            artigo,
            criteria,
            model=model,
            temperature=temperature,
            tokens=tokens,
            ollama_url=ollama_url,
            extra_prompt=extra_prompt,
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(_classify, index, artigo)
            for index, artigo in enumerate(artigos)
        ]

        for future in as_completed(futures):
            index, result = future.result()
            results[index] = result

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
    max_workers = data.get("maxWorkers")

    results = analisar(criterios_inclusao, criterios_exclusao, artigos, model, temperature, tokens, ollama_url, extra_prompt, max_workers)

    print(json.dumps(results, ensure_ascii=False))
