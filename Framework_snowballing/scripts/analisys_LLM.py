import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from services.prompt import (
    ANSWER_ERROR,
    criteria_from_text,
    expected_criteria_ids,
    generate_messages,
    parse_criteria_response,
    response_schema,
)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_LLM_WORKERS = 8
# Teto, nao estimativa: so se paga o que o modelo gera, mas a OpenRouter
# reserva saldo pelo teto de cada chamada em paralelo. Modelos com raciocinio
# gastam parte do limite antes do JSON: aumente LLM_MAX_TOKENS para eles.
DEFAULT_MAX_TOKENS = 1000
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
    entao so esse artigo vira "error"."""


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


def _env_flag(name, default):
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


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
    details = usage.get("completion_tokens_details") or {}
    print(
        f"[LLM USAGE] model={data.get('model')} "
        f"prompt_tokens={usage.get('prompt_tokens')} "
        f"completion_tokens={usage.get('completion_tokens')} "
        f"reasoning_tokens={details.get('reasoning_tokens')} "
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


def _call_llm(messages, schema):
    model = _model_name()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": _coerce_temperature(os.getenv("LLM_TEMPERATURE")),
        "max_tokens": _coerce_positive_int(os.getenv("LLM_MAX_TOKENS"), DEFAULT_MAX_TOKENS),
        # So roteia para provedores que respeitam todos os parametros enviados
        # (schema, reasoning); sem isso a OpenRouter pode ignora-los em silencio.
        "provider": {"require_parameters": True},
    }
    # Nem todo modelo aceita JSON schema (ex.: variantes :free). Desligado, o
    # formato vem so das instrucoes do prompt e parse_criteria_response extrai
    # o JSON do texto.
    if _env_flag("LLM_STRUCTURED_OUTPUT", True):
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "article_screening",
                "strict": True,
                "schema": schema,
            },
        }
    if _env_flag("LLM_REASONING", False):
        effort = os.getenv("LLM_REASONING_EFFORT", "").strip().lower()
        payload["reasoning"] = {"effort": effort} if effort else {"enabled": True}
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


# Resposta vazia ou fora do formato e intermitente (sobretudo sem JSON schema,
# como nos modelos :free): refaz a chamada antes de marcar o artigo com "error".
INVALID_RESPONSE_ATTEMPTS = 2


def classificar_artigo(article, criteria, extra_prompt=""):
    title = article.get("title", "")
    messages = generate_messages(article, criteria, extra_prompt)
    schema = response_schema(criteria)
    results = {criterion_id: ANSWER_ERROR for criterion_id in expected_criteria_ids(criteria)}

    for attempt in range(1, INVALID_RESPONSE_ATTEMPTS + 1):
        try:
            content = _call_llm(messages, schema)
        except LLMUpstreamError as e:
            # Recusa do provedor ja foi repetida dentro de _call_llm.
            print(f"[ERRO LLM] {title[:80]}: {e}", file=sys.stderr)
            break
        except ValueError as e:
            reason = str(e)
        else:
            results = parse_criteria_response(content, criteria)
            if ANSWER_ERROR not in results.values():
                break
            reason = f"resposta invalida: {content[:200]}"
        print(f"[ERRO LLM {attempt}/{INVALID_RESPONSE_ATTEMPTS}] {title[:80]}: {reason}", file=sys.stderr)

    return {"title": title, "results": results}


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


def analisar(criterios_inclusao, criterios_exclusao, artigos, extra_prompt=""):
    """Uma chamada a LLM por artigo, com todos os criterios."""
    criteria = criteria_from_text(criterios_inclusao, criterios_exclusao)
    tasks = [
        (lambda artigo=artigo: classificar_artigo(artigo, criteria, extra_prompt=extra_prompt))
        for artigo in artigos
    ]
    worker_count = min(
        _coerce_positive_int(os.getenv("LLM_MAX_WORKERS"), DEFAULT_LLM_WORKERS),
        max(len(tasks), 1),
    )
    return _run_parallel(tasks, worker_count)


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
        # criteriaMetadata ainda chega do frontend, mas por enquanto todos os
        # metadados vao para o prompt (ver METADATA_FIELDS em services/prompt.py).
        results = analisar(
            data.get("criteriosInclusao", ""),
            data.get("criteriosExclusao", ""),
            data.get("artigos", []),
            extra_prompt=data.get("extraPrompt", ""),
        )
    except LLMFatalError as error:
        # {"error": ...} no stdout + exit 1 e o contrato do PythonRunner para
        # falha esperada: a mensagem chega ao usuario em vez do stderr cru.
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(results, ensure_ascii=False))
