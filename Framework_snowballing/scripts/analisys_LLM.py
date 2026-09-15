import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from services.prompt import (
    criteria_from_text,
    expected_criteria_ids,
    generate_batch_prompt,
    generate_prompt,
)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_LLM_WORKERS = 4
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_TOKENS = 4000
DEFAULT_TIMEOUT_SECONDS = 120
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 30
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class LLMFatalError(RuntimeError):
    """Falha que nao adianta repetir por artigo: chave invalida, sem credito,
    modelo inexistente ou OpenRouter fora do ar. Interrompe a analise inteira
    em vez de multiplicar chamadas pagas que vao falhar do mesmo jeito."""


class LLMUpstreamError(ValueError):
    """O provedor escolhido pela OpenRouter recusou a chamada mesmo apos as
    tentativas (ex.: filtro de conteudo da Azure). E especifico do conteudo,
    entao o lote e refeito artigo a artigo e so o artigo problematico vira
    "error"."""


def _coerce_positive_int(value, default):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _coerce_temperature(value, default=0.0):
    try:
        return min(max(float(value), 0.0), 2.0)
    except (TypeError, ValueError):
        return default


def _model_name():
    return os.getenv("LLM_MODEL", "").strip() or DEFAULT_MODEL


def _fallback_models(primary):
    raw = os.getenv("LLM_FALLBACK_MODELS", "")
    models = []
    for model in raw.split(","):
        model = model.strip()
        if model and model != primary and model not in models:
            models.append(model)
    return models


def _api_key():
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise LLMFatalError("OPENROUTER_API_KEY nao configurada no .env.")
    return api_key


def _error_message(response):
    try:
        error = response.json().get("error")
    except ValueError:
        return response.text[:300]

    if isinstance(error, dict):
        message = error.get("message") or ""
        # "Provider returned error" sozinho nao diz nada; o motivo real do
        # provedor vem em metadata.raw.
        raw = (error.get("metadata") or {}).get("raw")
        if raw:
            message = f"{message} ({str(raw)[:300]})"
        return message or json.dumps(error, ensure_ascii=False)[:300]

    return str(error or response.text[:300])


def _is_upstream_error(status_code, message):
    # 400 vindo do provedor, e nao da validacao da OpenRouter: outra tentativa
    # pode ser roteada para outro provedor (OpenAI em vez de Azure, etc.).
    return status_code == 400 and message.startswith("Provider returned error")


def _retry_delay(response, attempt):
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after and retry_after.isdigit():
        return min(int(retry_after), MAX_RETRY_DELAY_SECONDS)
    return min(2 ** attempt, MAX_RETRY_DELAY_SECONDS)


def _log_usage(data):
    usage = data.get("usage") or {}
    print(
        f"[LLM USAGE] model={data.get('model')} "
        f"prompt_tokens={usage.get('prompt_tokens')} "
        f"completion_tokens={usage.get('completion_tokens')} "
        f"cost={usage.get('cost')}",
        file=sys.stderr,
    )


def _parse_completion(data):
    if data.get("error"):
        raise ValueError(f"OpenRouter retornou erro: {data['error']}")

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Resposta da OpenRouter sem choices")

    _log_usage(data)
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise ValueError(f"Resposta sem conteudo (finish_reason={choices[0].get('finish_reason')})")

    return content.strip()


def _call_llm(prompt, response_schema, schema_name, max_tokens):
    model = _model_name()
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": _coerce_temperature(os.getenv("LLM_TEMPERATURE")),
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": response_schema,
            },
        },
        # So roteia para provedores que respeitam response_format; sem isso a
        # OpenRouter pode escolher um que ignora o schema e devolve texto livre.
        "provider": {"require_parameters": True},
    }
    fallbacks = _fallback_models(model)
    if fallbacks:
        payload["models"] = [model, *fallbacks]

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "X-Title": "Snowballing Framework",
    }
    timeout = _coerce_positive_int(os.getenv("LLM_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS)

    last_error = None
    upstream_failure = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = None
        upstream_failure = False
        try:
            response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as error:
            last_error = error
        else:
            if response.ok:
                return _parse_completion(response.json())
            message = _error_message(response)
            upstream_failure = _is_upstream_error(response.status_code, message)
            if response.status_code not in RETRYABLE_STATUS and not upstream_failure:
                raise LLMFatalError(
                    f"OpenRouter recusou a requisicao (HTTP {response.status_code}): {message}"
                )
            last_error = f"HTTP {response.status_code}: {message}"

        if attempt < MAX_ATTEMPTS:
            delay = _retry_delay(response, attempt)
            print(f"[LLM RETRY {attempt}] {last_error}; nova tentativa em {delay}s", file=sys.stderr)
            time.sleep(delay)

    if upstream_failure:
        raise LLMUpstreamError(f"Provedor recusou a chamada apos {MAX_ATTEMPTS} tentativas: {last_error}")
    raise LLMFatalError(f"OpenRouter nao respondeu apos {MAX_ATTEMPTS} tentativas: {last_error}")


def _max_tokens_for(article_count, criteria):
    criteria_count = max(len(expected_criteria_ids(criteria)), 1)
    estimated_json_tokens = 32 + article_count * (16 + criteria_count * 10)
    cap = _coerce_positive_int(os.getenv("LLM_MAX_TOKENS"), DEFAULT_MAX_TOKENS)
    # Folga de 2x: cortar o JSON no meio invalida o lote inteiro.
    return min(cap, max(256, estimated_json_tokens * 2))


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
            criterion_id: "error"
            for criterion_id in expected_criteria_ids(criteria)
        }
    }


def _has_errors(result):
    return any(value == "error" for value in (result.get("results") or {}).values())


def _normalize_search_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).lower()


def _normalized_language(value):
    normalized = _normalize_search_text(value).strip()
    aliases = {
        "en": "english",
        "eng": "english",
        "english": "english",
        "ingles": "english",
        "pt": "portuguese",
        "por": "portuguese",
        "portuguese": "portuguese",
        "portugues": "portuguese",
        "es": "spanish",
        "spa": "spanish",
        "spanish": "spanish",
        "espanhol": "spanish",
    }
    return aliases.get(normalized)


def _criterion_language(description):
    normalized = _normalize_search_text(description)
    language_terms = {
        "english": ("english", "ingles"),
        "portuguese": ("portuguese", "portugues"),
        "spanish": ("spanish", "espanhol"),
    }
    for language, terms in language_terms.items():
        if any(term in normalized for term in terms):
            return language
    return None


_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")


def _coerce_year(value):
    if value in (None, "", "-"):
        return None
    match = _YEAR_PATTERN.search(str(value))
    return int(match.group()) if match else None


def _criterion_year_constraint(description):
    normalized = _normalize_search_text(description)
    match = _YEAR_PATTERN.search(normalized)
    if not match:
        return None

    year = int(match.group())
    before_ctx = normalized[max(0, match.start() - 20):match.start()]
    after_ctx = normalized[match.end():match.end() + 20]

    if "or later" in after_ctx or "or after" in after_ctx:
        return (">=", year)
    if "or earlier" in after_ctx or "or before" in after_ctx:
        return ("<=", year)
    if any(term in before_ctx for term in ("before", "prior to", "earlier than", "up to", "until")):
        return ("<", year)
    if "since" in before_ctx:
        return (">=", year)
    if any(term in before_ctx for term in ("after", "later than")):
        return (">", year)

    return ("==", year)


def _year_matches(article_year, operator, year):
    if operator == "==":
        return article_year == year
    if operator == "<":
        return article_year < year
    if operator == "<=":
        return article_year <= year
    if operator == ">":
        return article_year > year
    if operator == ">=":
        return article_year >= year
    return False


def _apply_deterministic_metadata(article, results, criteria):
    article_language = _normalized_language(article.get("language"))
    article_year = _coerce_year(article.get("year"))

    descriptions = {
        **criteria.get("Inclusion", {}),
        **criteria.get("Exclusion", {}),
    }
    for criterion_id, description in descriptions.items():
        required_language = _criterion_language(description)
        if required_language and article_language:
            results[criterion_id] = "Yes" if article_language == required_language else "No"
            continue

        if article_year is not None:
            year_constraint = _criterion_year_constraint(description)
            if year_constraint:
                operator, year = year_constraint
                results[criterion_id] = "Yes" if _year_matches(article_year, operator, year) else "No"

    return results


def _criteria_schema(criteria):
    criterion_ids = expected_criteria_ids(criteria)
    return {
        "type": "object",
        "properties": {
            criterion_id: {
                "type": "string",
                "enum": ["Yes", "No", "Unsure"],
            }
            for criterion_id in criterion_ids
        },
        "required": criterion_ids,
        "additionalProperties": False,
    }


def _single_response_schema(criteria):
    return {
        "type": "object",
        "properties": {"criteria": _criteria_schema(criteria)},
        "required": ["criteria"],
        "additionalProperties": False,
    }


def _batch_response_schema(criteria):
    # Sem minItems/maxItems: nem todo provedor aceita essas chaves em modo
    # strict. Artigo que faltar na resposta e refeito individualmente.
    return {
        "type": "object",
        "properties": {
            "articles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "criteria": _criteria_schema(criteria),
                    },
                    "required": ["index", "criteria"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["articles"],
        "additionalProperties": False,
    }


def classificar_artigo(article, criteria, extra_prompt=""):
    title = article.get("title", "")
    prompt = generate_prompt(
        article=article,
        criteria=criteria,
        extra_prompt=extra_prompt,
    )

    try:
        data = _extract_json_object(_call_llm(
            prompt,
            _single_response_schema(criteria),
            "article_screening",
            max_tokens=_max_tokens_for(1, criteria),
        ))
        return _normalize_result_from_raw(article, data, criteria)

    except (ValueError, TypeError, KeyError) as e:
        print(f"[ERRO LLM] {e}", file=sys.stderr)
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

    results = {
        criterion_id: _normalize_criterion_answer(raw_criteria.get(criterion_id))
        for criterion_id in expected_criteria_ids(criteria)
    }
    return {
        "title": article.get("title", ""),
        "results": _apply_deterministic_metadata(article, results, criteria),
    }


def classificar_lote(articles, criteria, extra_prompt="", criteria_metadata=None):
    if not articles:
        return []

    prompt = generate_batch_prompt(
        articles=articles,
        criteria=criteria,
        extra_prompt=extra_prompt,
        criteria_metadata=criteria_metadata,
    )

    try:
        data = _extract_json_value(
            _call_llm(
                prompt,
                _batch_response_schema(criteria),
                "batch_screening",
                max_tokens=_max_tokens_for(len(articles), criteria),
            )
        )

        raw_items = data.get("articles") if isinstance(data, dict) else data
        if not isinstance(raw_items, list):
            raise ValueError("Resposta batch sem lista de artigos")

    except (ValueError, TypeError, KeyError) as e:
        print(f"[ERRO LLM batch] {e}", file=sys.stderr)
        return [classificar_artigo(article, criteria, extra_prompt=extra_prompt) for article in articles]

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

    results = [
        _normalize_result_from_raw(article, by_index.get(index, {}), criteria)
        for index, article in enumerate(articles)
    ]

    # So refaz, um a um, os artigos que faltaram ou vieram invalidos no lote.
    for index, article in enumerate(articles):
        if _has_errors(results[index]):
            results[index] = classificar_artigo(article, criteria, extra_prompt=extra_prompt)

    return results


def _chunked(items, size):
    size = max(1, size)
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _run_parallel(tasks, worker_count):
    """Executa tasks (callables sem argumento) preservando a ordem. Um
    LLMFatalError em qualquer uma cancela as que ainda nao comecaram."""
    if worker_count <= 1:
        return [task() for task in tasks]

    results = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(task): index for index, task in enumerate(tasks)}
        try:
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        except BaseException:
            for future in futures:
                future.cancel()
            raise

    return results


def _worker_count(task_count):
    return min(
        _coerce_positive_int(os.getenv("LLM_MAX_WORKERS"), DEFAULT_LLM_WORKERS),
        max(task_count, 1),
    )


def analisar(criterios_inclusao, criterios_exclusao, artigos, extra_prompt="", criteria_metadata=None):
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    batch_size = _coerce_positive_int(os.getenv("LLM_BATCH_SIZE"), DEFAULT_BATCH_SIZE)
    batches = list(_chunked(artigos, batch_size))

    tasks = [
        (lambda batch=batch: classificar_lote(
            batch,
            criteria,
            extra_prompt=extra_prompt,
            criteria_metadata=criteria_metadata,
        ))
        for batch in batches
    ]

    flattened = []
    for batch_result in _run_parallel(tasks, _worker_count(len(tasks))):
        flattened.extend(batch_result or [])

    return flattened


def analisar_individual(criterios_inclusao, criterios_exclusao, artigos, extra_prompt=""):
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    tasks = [
        (lambda artigo=artigo: classificar_artigo(artigo, criteria, extra_prompt=extra_prompt))
        for artigo in artigos
    ]
    return _run_parallel(tasks, _worker_count(len(tasks)))


if __name__ == "__main__":
    # O Node troca JSON em UTF-8; no Windows o padrao do Python e cp1252, que
    # corrompe titulos/abstracts (ex.: "‐" vira surrogate solto e a OpenRouter
    # recusa o corpo como JSON invalido).
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    input_json = sys.stdin.read()
    data = json.loads(input_json)

    try:
        results = analisar(
            data.get("criteriosInclusao", ""),
            data.get("criteriosExclusao", ""),
            data.get("artigos", []),
            extra_prompt=data.get("extraPrompt", ""),
            criteria_metadata=data.get("criteriaMetadata") or {},
        )
    except LLMFatalError as error:
        # {"error": ...} no stdout + exit 1 e o contrato do PythonRunner para
        # falha esperada: a mensagem chega ao usuario em vez do stderr cru.
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False))
