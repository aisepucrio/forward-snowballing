def gerar_prompt(title, summary, inc, exc):
    inc = _split_criterios(inc)
    exc = _split_criterios(exc)

    inc_ids = [f"IC{i + 1}" for i in range(len(inc))]
    exc_ids = [f"EC{i + 1}" for i in range(len(exc))]

    prompt = f"""
    You are a expert researcher conducing a Systematic Review.
    Evaluate the article based on the inclusion and exclusion criteria.

    INCLUSION CRITERIA (mark Yes/No)
    {chr(10).join([f"- {inc_ids[i]}: {inc[i]}" for i in range(len(inc))])}

    EXCLUSION CRITERIA (mark Yes/No)
    {chr(10).join([f"- {exc_ids[i]}: {exc[i]}" for i in range(len(exc))])}

    ARTICLE TO ANALYZE:
    - title: {title}
    - abstract: {summary}

    EXACT OUTPUT FORMAT (JSON):
    {{
      "title": "<repita o titulo do artigo>",
      "results": {{
        "{'": "Yes|No|Not conclusive", "'.join(inc_ids + exc_ids)}": "Yes|No|Not conclusive"
      }},
      "Decision": {{
        "decision": "inclusion|exclusion|not conclusive",
      }}
    }}

    Rules:
    - Use only "Yes", "No" or "Not conclusive" in the result for each criteria.
    - If any exclusion criterion is marked "Yes", the decision must be "exclusion". STOP and return the results json.
    - If any inclusion criterion is marked "No", the decision must be "exclusion". STOP and return the results json.
    - Only if there is any "Not conclusive" in the criteria results, the decision must be "not conclusive".
    - Only if all inclusion criteria are "Yes" and all exclusion criteria are "No", the decision can be "inclusion".
    - Do not include any keys other than the requested ones.
    - Return only the JSON, without any markdown or extra text.
    """
    return prompt

def _split_criterios(texto: str):
    return [c.strip() for c in (texto or "").splitlines() if c.strip()]