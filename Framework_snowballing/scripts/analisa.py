import sys
import json
import ollama


MODEL_NAME = "llama3.2:3b"


def _split_criterios(texto: str):
    # Divide por linha e remove vazios
    return [c.strip() for c in (texto or "").splitlines() if c.strip()]


def classificar_artigo(title, summary, criterios_inclusao, criterios_exclusao):
    inc = _split_criterios(criterios_inclusao)
    exc = _split_criterios(criterios_exclusao)

    # IDs estáveis (melhor que usar o texto inteiro como chave)
    inc_ids = [f"IC{i+1}" for i in range(len(inc))]
    exc_ids = [f"EC{i+1}" for i in range(len(exc))]

    # Prompt pedindo JSON estrito
    prompt = f"""
Você é um pesquisador de Engenharia de Software conduzindo uma Revisão Sistemática.
Avalie o artigo com base nos critérios. Responda SOMENTE com JSON VÁLIDO (sem markdown, sem texto extra).

ARTIGO
- title: {title}
- abstract: {summary}

CRITÉRIOS DE INCLUSÃO (marque Sim/Não)
{chr(10).join([f"- {inc_ids[i]}: {inc[i]}" for i in range(len(inc))])}

CRITÉRIOS DE EXCLUSÃO (marque Sim/Não)
{chr(10).join([f"- {exc_ids[i]}: {exc[i]}" for i in range(len(exc))])}

FORMATO EXATO DE SAÍDA (JSON):
{{
  "Título": "<repita o título do artigo>",
  "Resultados": {{
    "{'": "Sim|Não", "'.join(inc_ids + exc_ids)}": "Sim|Não"
  }},
  "ResumoDecisao": {{
    "decisao": "inclusão|exclusão",
    "confianca": 0.0,
    "justificativa_curta": "<1 frase curta>"
  }}
}}

Regras:
- Use apenas "Sim" ou "Não" nas chaves de Resultados.
- "confianca" deve ser um número entre 0.0 e 1.0.
- Não inclua nenhuma chave além das pedidas.
"""

    try:
        resp = ollama.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            options={
                "temperature": 0.1,   # mais determinístico
                "num_predict": 600    # limita tamanho
            }
        )

        text = resp["message"]["content"].strip()

        # Algumas vezes o modelo pode colocar lixo antes/depois.
        # Vamos tentar extrair o primeiro objeto JSON.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Resposta não contém JSON")

        json_text = text[start:end+1]
        data = json.loads(json_text)

        # Validações simples
        if "Título" not in data or "Resultados" not in data:
            raise ValueError("JSON faltando campos obrigatórios")

        return data

    except Exception as e:
        print(f"[ERRO Ollama] ao classificar artigo '{title}': {e}", file=sys.stderr)
        return {
            "Título": title or "",
            "Resultados": {"Criteria": "It was not possible to analyze the criterion. Please check the submitted data or try again later."},
            "ResumoDecisao": {
                "decisao": "exclusão",
                "confianca": 0.0,
                "justificativa_curta": "Falha ao processar com o modelo."
            }
        }


def analisar(criterios_inclusao, criterios_exclusao, artigos):
    resultados = []
    for artigo in artigos:
        title = artigo.get("title", "")
        abstract = artigo.get("abstract", "")

        out = classificar_artigo(title, abstract, criterios_inclusao, criterios_exclusao)
        resultados.append(out)

    return resultados


if __name__ == "__main__":
    input_json = sys.stdin.read()
    data = json.loads(input_json)

    criterios_inclusao = data.get("criteriosInclusao", "")
    criterios_exclusao = data.get("criteriosExclusao", "")
    artigos = data.get("artigos", [])

    resultados = analisar(criterios_inclusao, criterios_exclusao, artigos)
    print(json.dumps(resultados, ensure_ascii=False))