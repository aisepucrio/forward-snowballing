import google.generativeai as genai
import sys
import json

API_KEY='API_KEY'

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel('gemini-2.5-flash')


def extrair_resultados(tabela_texto):
    linhas = [l.strip() for l in tabela_texto.strip().splitlines() if l.strip()]
    if len(linhas) < 2:
        return []

    # Cabeçalhos, ex: | Título | Critério 1 | Critério 2 |
    cabecalhos = [c.strip() for c in linhas[0].strip('|').split('|')]

    resultados = []
    for linha in linhas[1:]:
        if "---" in linha:
            continue  # Ignora linha de separação markdown
        valores = [v.strip() for v in linha.strip('|').split('|')]
        if len(valores) != len(cabecalhos):
            continue
        artigo_resultado = {
            "Título": valores[0],
            "Resultados": {crit: val for crit, val in zip(cabecalhos[1:], valores[1:])}
        }
        resultados.append(artigo_resultado)

    return resultados


def classificar_artigo(title, summary, criterios_inclusao, criterios_exclusao):
    prompt = f"""
Você é um pesquisador de engenharia de software conduzindo uma revisão sistemática.
Classifique o artigo abaixo como 'inclusão' ou 'exclusão' com base nos critérios.

Título: {title}
Resumo: {summary}

Critérios de Inclusão:
{criterios_inclusao}

Critérios de Exclusão:
{criterios_exclusao}

Responda com uma tabela. A primeira coluna deve ser o Título. As demais colunas devem corresponder aos critérios (Critério 1, Critério 2, etc).
Use 'Sim' ou 'Não' para cada célula.
"""

    try:
        resposta = model.generate_content(prompt)
        return resposta.text
    except Exception as e:
        print(f"[ERRO Gemini] ao classificar artigo '{title}': {e}", file=sys.stderr)
        return "Erro"


def classificar_artigo(title, summary, criterios_inclusao, criterios_exclusao):
    # Lista os critérios separadamente
    lista_inclusao = [c.strip() for c in criterios_inclusao.strip().split('\n') if c.strip()]
    lista_exclusao = [c.strip() for c in criterios_exclusao.strip().split('\n') if c.strip()]

    colunas = []

    # Prefixa os critérios dinamicamente
    for i, crit in enumerate(lista_inclusao):
        colunas.append(f"Inclusion Criteria  {i+1}: {crit}")
    for i, crit in enumerate(lista_exclusao):
        colunas.append(f"Exclusion Criteria {i+1}: {crit}")

    colunas_str = " | ".join(colunas)

    prompt = f"""
Você é um pesquisador de engenharia de software conduzindo uma revisão sistemática.
Analise o artigo abaixo com base nos critérios fornecidos.

Título do Artigo: {title}
Resumo: {summary}

Critérios de Inclusão:
{criterios_inclusao}

Critérios de Exclusão:
{criterios_exclusao}

Responda apenas com uma tabela em Markdown com as colunas a seguir:

| Título | {colunas_str} |

Para cada critério, responda apenas com "Sim" ou "Não".

A primeira linha da tabela deve conter os cabeçalhos. A segunda linha deve conter a avaliação do artigo.
Não adicione nenhuma explicação antes ou depois da tabela.
"""

    try:
        resposta = model.generate_content(prompt)
        return resposta.text
    except Exception as e:
        print(f"[ERRO Gemini] ao classificar artigo '{title}': {e}", file=sys.stderr)
        return "Erro"
def analisar(criterios_inclusao, criterios_exclusao, artigos):
    resultados = []
    for artigo in artigos:
        raw = classificar_artigo(
            artigo.get("title", ""),
            artigo.get("abstract", ""),
            criterios_inclusao,
            criterios_exclusao
        )
        try:
            if raw == "Erro":
                raise ValueError("Erro ao chamar o Gemini")

            lista_resultados = extrair_resultados(raw)
            if lista_resultados:
                resultados.append(lista_resultados[0])  # Resultado do artigo atual
            else:
                raise ValueError("Sem resultados extraídos")
        except Exception as e:
            print(f"[ERRO Análise] Artigo '{artigo.get('title', '')}': {e}", file=sys.stderr)
            criterios = {f"Criteria": "It was not possible to analyze the criterion. Please check the submitted data or try again later." for i in range(1)}
            resultados.append({
                "Título": artigo.get("title", ""),
                "Resultados": criterios
            })
    return resultados


if __name__ == "__main__":
    input_json = sys.stdin.read()
    data = json.loads(input_json)
    criterios_inclusao = data.get("criteriosInclusao", "")
    criterios_exclusao = data.get("criteriosExclusao", "")
    artigos = data.get("artigos", [])

    resultados = analisar(criterios_inclusao, criterios_exclusao, artigos)
    print(json.dumps(resultados, ensure_ascii=False))
