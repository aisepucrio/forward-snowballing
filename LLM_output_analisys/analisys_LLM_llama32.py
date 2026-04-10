import json
import re
import sys
import time
from pathlib import Path
import ollama

BASE_DIR = Path(__file__).resolve().parent
RESULTADOS_PATH = BASE_DIR / "resultados_llama32.json"

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
    Voce e um pesquisador de Engenharia de Software conduzindo uma Revisao Sistematica.
    Avalie o artigo com base nos criterios. Responda SOMENTE com JSON VALIDO (sem markdown, sem texto extra).

    ARTIGO
    - title: {title}
    - abstract: {summary}

    CRITERIOS DE INCLUSAO (marque Sim/Nao)
    {chr(10).join([f"- {inc_ids[i]}: {inc[i]}" for i in range(len(inc))])}

    CRITERIOS DE EXCLUSAO (marque Sim/Nao)
    {chr(10).join([f"- {exc_ids[i]}: {exc[i]}" for i in range(len(exc))])}

    FORMATO EXATO DE SAIDA (JSON):
    {{
      "title": "<repita o titulo do artigo>",
      "results": {{
        "{'": "Sim|Nao", "'.join(inc_ids + exc_ids)}": "Sim|Nao"
      }},
      "ResumoDecisao": {{
        "decisao": "inclusao|exclusao",
        "confianca": 0.0-1.0
      }}
    }}

    Regras:
    - Use apenas "Sim" ou "Nao" nas chaves de results.
    - "confianca" deve ser um numero entre 0.0 e 1.0.
    - Nao inclua nenhuma chave alem das pedidas.
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
