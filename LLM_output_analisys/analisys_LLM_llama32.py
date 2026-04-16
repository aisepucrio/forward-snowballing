import json
import re
import sys
import time
from pathlib import Path
import ollama

BASE_DIR = Path(__file__).resolve().parent
RESULTADOS_PATH = BASE_DIR / "resultados_llama32.json"
if not RESULTADOS_PATH.exists() or not RESULTADOS_PATH.read_text(encoding="utf-8").strip():
    RESULTADOS_PATH.write_text("[]", encoding="utf-8")


def _split_criterios(texto: str):
    return [c.strip() for c in (texto or "").splitlines() if c.strip()]


def extract_retry_delay_seconds(error) -> int | None:
    message = str(error)

    match = re.search(r"'retryDelay':\s*'(\d+)s'", message)
    if match:
        return int(match.group(1))

    match = re.search(r"Please retry in\s+(\d+(?:\.\d+)?)s", message)
    if match:
        return max(1, int(float(match.group(1))))

    return None


def classificar_artigo(title, summary, criterios_inclusao, criterios_exclusao):
    inc = _split_criterios(criterios_inclusao)
    exc = _split_criterios(criterios_exclusao)

    inc_ids = [f"IC{i + 1}" for i in range(len(inc))]
    exc_ids = [f"EC{i + 1}" for i in range(len(exc))]

    prompt = f"""
    You are a expert researcher conducing a Systematic Review.
    Evaluate the article based on the criteria. Answer ONLY with VALID JSON (no markdown, no extra text).

    ARTICLE TO ANALYZE:
    - title: {title}
    - abstract: {summary}

    INCLUSION CRITERIA (mark Yes/No)
    {chr(10).join([f"- {inc_ids[i]}: {inc[i]}" for i in range(len(inc))])}

    EXCLUSION CRITERIA (mark Yes/No)
    {chr(10).join([f"- {exc_ids[i]}: {exc[i]}" for i in range(len(exc))])}

    EXACT OUTPUT FORMAT (JSON):
    {{
      "title": "<repita o titulo do artigo>",
      "results": {{
        "{'": "Yes|No", "'.join(inc_ids + exc_ids)}": "Yes|No"
      }},
      "Decision": {{
        "decision": "inclusion|exclusion",
        "confidence": 0.0-1.0
      }}
    }}

    Regras:
    - Use only "Yes" ou "No" in the result for each criteria.
    - "confidence" must be a number between 0.0 and 1.0.
    - If any exclusion criterion is marked "Yes", the decision must be "exclusion".
    - If any inclusion criterion is marked "No", the decision must be "exclusion".
    - Only if all inclusion criteria are "Yes" and all exclusion criteria are "No", the decision can be "inclusion".
    - Do not include any keys other than the requested ones.
    """

    try:
        resp = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,
                "num_predict": 600,
    },
)
        text = resp["message"]["content"].strip()

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Resposta nao contem JSON")

        json_text = text[start:end + 1]
        data = json.loads(json_text)

        if "title" not in data or "results" not in data:
            raise ValueError("JSON faltando campos obrigatorios")

        return data

    except Exception as e:
        return {
            "title": title or "",
            "results": {
                "Criteria": "It was not possible to analyze the criterion. Please check the submitted data or try again later."
            },
            "ResumoDecisao": {
                "decisao": "exclusao",
                "confianca": 0.0,
                "justificativa_curta": "Falha ao processar com o modelo.",
            },
        }



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

        if title_normalizado in titulos_processados:
            print(f"Artigo ja processado, pulando: {title}", file=sys.stderr)
            continue


        out = classificar_artigo(title, abstract, criterios_inclusao, criterios_exclusao)


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
