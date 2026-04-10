def gerar_prompt(title, summary, inc, exc):

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
        "confianca": 0.0,
        "justificativa_curta": "<1 frase curta>"
      }}
    }}

    Regras:
    - Use apenas "Sim" ou "Nao" nas chaves de results.
    - "confianca" deve ser um numero entre 0.0 e 1.0.
    - Nao inclua nenhuma chave alem das pedidas.
    """
    return prompt

def _split_criterios(texto: str):
    return [c.strip() for c in (texto or "").splitlines() if c.strip()]