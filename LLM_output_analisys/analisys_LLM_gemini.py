import json
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from prompt_generator import gerar_prompt

BASE_DIR = Path(__file__).resolve().parent
RESULTADOS_PATH = BASE_DIR / "resultados_gemini.json"

load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.1-flash-lite-preview"

if not API_KEY:
    raise ValueError("GEMINI_API_KEY nao definida no arquivo .env")

client = genai.Client(api_key=API_KEY)
REQUEST_INTERVAL_SECONDS = 15


class RetryableGeminiError(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Retry apos {retry_after_seconds}s")



def extract_retry_delay_seconds(error) -> int | None:
    message = str(error)

    match = re.search(r"'retryDelay':\s*'(\d+)s'", message)
    if match:
        return int(match.group(1))

    match = re.search(r"Please retry in\s+(\d+(?:\.\d+)?)s", message)
    if match:
        return max(1, int(float(match.group(1))))

    return None


def classificar_artigo(title, prompt):
    try:
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "temperature": 0.1,
            },
        )

        text = (resp.text or "").strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            print("--\n" + text + "\n--")
            raise ValueError("Resposta nao contem JSON")

        json_text = text[start:end + 1]
        data = json.loads(json_text)

        if "title" not in data or "results" not in data:
            raise ValueError("JSON faltando campos obrigatorios")

        return data

    except Exception as e:
        retry_delay = extract_retry_delay_seconds(e)
        if retry_delay is not None:
            print(
                f"[ERRO Gemini] Falha de quota ao classificar artigo '{title}'. "
                f"Aguardando {retry_delay}s para tentar novamente...",
                file=sys.stderr,
            )
            raise RetryableGeminiError(retry_delay) from e
        else:
            print(
                f"[ERRO Gemini] Falha ao classificar artigo '{title}'. "
                f"Erro: {e}. "
                f"Aguardando 15s para tentar novamente...",
                file=sys.stderr,
            )
            raise RetryableGeminiError(retry_delay) from e



def normalizar_titulo(title):
    return str(title or "").strip().lower()


def carregar_resultados_existentes():
    if not RESULTADOS_PATH.exists():
        return []

    with RESULTADOS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def salvar_resultados_existentes(results):
    with RESULTADOS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def analisar(criterios_inclusao, criterios_exclusao, artigos):
    results = carregar_resultados_existentes()

    titulos_processados = {
        normalizar_titulo(item.get("title", ""))
        for item in results
        if item.get("title")
    }

    for artigo in artigos:
        title = artigo.get("title", "")
        abstract = artigo.get("abstract", "")
        title_normalizado = normalizar_titulo(title)
        prompt = gerar_prompt(title, abstract, criterios_inclusao, criterios_exclusao)

        if title_normalizado in titulos_processados:
            print(f"Artigo ja processado, pulando: {title}", file=sys.stderr)
            continue

        if results:
            print(f"Aguardando {REQUEST_INTERVAL_SECONDS}s antes da proxima requisicao...", file=sys.stderr)
            time.sleep(REQUEST_INTERVAL_SECONDS)

        while True:
            try:
                out = classificar_artigo(title, prompt)
                break
            except RetryableGeminiError as retry_error:
                if retry_error.retry_after_seconds:
                    time.sleep(retry_error.retry_after_seconds)
                time.sleep(REQUEST_INTERVAL_SECONDS)

        results.append(out)
        titulos_processados.add(title_normalizado)

        with RESULTADOS_PATH.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


def gerar_analise(json_path):
    json_path = Path(json_path)

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    criterios_inclusao = data.get("criteriosInclusao", "")
    criterios_exclusao = data.get("criteriosExclusao", "")
    artigos = data.get("artigos", [])

    analisar(criterios_inclusao, criterios_exclusao, artigos)

if __name__ == "__main__":
    gerar_analise("articles.json")