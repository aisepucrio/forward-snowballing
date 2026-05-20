import sys
import json
import ollama

OLLAMA_URL = "http://11.0.0.35:11434/api/chat"
MODEL_NAME = "gemma4:31b"


def _split_criterios(texto: str):
    return [c.strip() for c in (texto or "").splitlines() if c.strip()]


def classificar_artigo(title, summary, criterios_inclusao, criterios_exclusao):
    inc = _split_criterios(criterios_inclusao)
    exc = _split_criterios(criterios_exclusao)

    inc_ids = [f"IC{i+1}" for i in range(len(inc))]
    exc_ids = [f"EC{i+1}" for i in range(len(exc))]


    prompt = f"""
Você é um pesquisador conduzindo uma Revisão Sistemática da Literatura.

Responda APENAS com JSON válido. Sem explicações, sem markdown.

ARTIGO:
Título: {title}
Resumo: {summary}

CRITÉRIOS DE INCLUSÃO:
{chr(10).join([f"{inc_ids[i]}: {inc[i]}" for i in range(len(inc))])}

CRITÉRIOS DE EXCLUSÃO:
{chr(10).join([f"{exc_ids[i]}: {exc[i]}" for i in range(len(exc))])}

FORMATO OBRIGATÓRIO DE SAÍDA:

{{
  "title": "{title}",
  "results": {{
    "IC1": "Sim ou Não",
    "IC2": "Sim ou Não",
    "EC1": "Sim ou Não",
    "EC2": "Sim ou Não"
  }}
}}

REGRAS IMPORTANTES:
- Use SOMENTE "Sim" ou "Não"
- Não invente chaves fora de IC/EC
- Se não tiver critério, ainda retorne o JSON completo
- responda SOMENTE com JSON válido. Sem explicações, sem texto fora do JSON.
"""


    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "options": {
            "temperature":0.1,
            "num_predict":600
            },
            "stream": False,
            "think": False
        }

        resp = requests.post(OLLAMA_URL,json=payload)
        resp.raise_for_status()

        text = resp.json()["message"]["content"].strip()

        # extrair JSON de forma segura
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("JSON não encontrado na resposta")

        json_text = text[start:end + 1]
        data = json.loads(json_text)

        # 🔥 GARANTIA DE ESTRUTURA (evita EC sumir)
        if "results" not in data:
            data["results"] = {}

        for ic in inc_ids:
            data["results"].setdefault(ic, "Não")

        for ec in exc_ids:
            data["results"].setdefault(ec, "Não")

        return data

    except Exception as e:
        print(f"[ERRO Ollama] {e}", file=sys.stderr)

        # fallback seguro
        return {
            "title": title,
            "results": {
                **{f"IC{i+1}": "Não" for i in range(len(inc))},
                **{f"EC{i+1}": "Não" for i in range(len(exc))}
            }
        }


def analisar(criterios_inclusao, criterios_exclusao, artigos):
    results = []

    for artigo in artigos:
        title = artigo.get("title", "")
        abstract = artigo.get("abstract", "")

        out = classificar_artigo(
            title,
            abstract,
            criterios_inclusao,
            criterios_exclusao
        )

        results.append(out)

    return results


if __name__ == "__main__":
    input_json = sys.stdin.read()
    data = json.loads(input_json)

    criterios_inclusao = data.get("criteriosInclusao", "")
    criterios_exclusao = data.get("criteriosExclusao", "")
    artigos = data.get("artigos", [])

    results = analisar(criterios_inclusao, criterios_exclusao, artigos)

    print(json.dumps(results, ensure_ascii=False))
