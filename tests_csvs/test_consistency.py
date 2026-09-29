import os
import csv
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FRAMEWORK_DIR = os.path.dirname(SCRIPT_DIR)

SCRIPTS_DIR = os.path.join(FRAMEWORK_DIR, "scripts")

RUN_FORWARD_PY = os.path.join(SCRIPTS_DIR, "run_forward.py")

# Cada entrada e buscada duas vezes. O run_backward foi eliminado (era
# subconjunto estrito do forward), entao a repeticao passou a ser do mesmo
# script — que e o que esta medida sempre quis: variacao entre execucoes.
# Agora as duas linhas trazem citacoes, e nao so uma delas.
EXECUCOES_POR_ENTRADA = 2

INPUT_CSV = os.path.join(SCRIPT_DIR, "tests_csvs.csv")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "result_searches.csv")

# Segundos de espera após cada busca, para não estourar o limite anônimo da
# Semantic Scholar (~1 req/s). Ajustável por variável de ambiente.
PAUSA_ENTRE_BUSCAS = float(os.getenv("PAUSA_ENTRE_BUSCAS", "2"))

# Teto por busca. Era 120s, apertado desde que a Semantic Scholar passou a ser
# consultada a 1 req/s: uma busca com muitas chamadas leva ~53s em média, e as
# mais pesadas passavam de 120s e entravam no CSV como TIMEOUT — falha do teto
# do teste, não do pipeline (o mesmo artigo buscado por DOI concluía normal).
# 300s dá folga para o pior caso sem deixar uma busca travada segurar a suíte.
TIMEOUT_POR_BUSCA = float(os.getenv("TIMEOUT_POR_BUSCA", "300"))

# Mesmo User-Agent do pipeline. O OpenAlex coloca no "polite pool" quem se
# identifica com um e-mail real pelo parâmetro mailto; fica opcional por
# variável de ambiente para não fixar no código o contato de ninguém.
USER_AGENT = "forward-snowballing-app/1.0"
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO", "").strip()


def is_doi(value):
    return value.startswith("10.") or ("/" in value and " " not in value)


def load_input_papers(csv_path):
    """
    Lê CADA LINHA do CSV como uma entrada totalmente independente.
    Se a linha for um DOI, passa apenas o DOI.
    Se for um título, passa apenas o título.
    """
    papers = []
    if not os.path.exists(csv_path):
        print(f"(ERRO) Arquivo não encontrado: {csv_path}")
        return papers

    # Lido linha a linha, não com csv.reader: o arquivo é uma coluna só, e
    # títulos de artigo costumam conter vírgula. O parser de CSV quebraria
    # "Software testing, verification and reliability" em duas colunas e o
    # script buscaria apenas "Software testing" — resultado errado com status
    # SUCCESS, sem nenhum sinal de que a entrada foi truncada.
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line_content = raw_line.strip()
            if not line_content:
                continue

            if line_content.lower() in ["title", "doi", "input_title", "input_doi"]:
                continue

            if is_doi(line_content):
                papers.append({"title": "", "doi": line_content})
            else:
                papers.append({"title": line_content, "doi": ""})

    return papers


def fetch_openalex_counts(doi):
    """
    Consulta o OpenAlex direto, fora do pipeline, para ter uma referência
    externa ao lado do que a busca coletou.

    Só por DOI, e o DOI usado é o resolved_doi que o próprio pipeline devolveu.
    Buscar por título e pegar o primeiro resultado podia comparar a busca com
    um artigo diferente, sem nenhum sinal disso no CSV. Sem DOI, as colunas
    ficam vazias: é melhor não ter a comparação do que ter uma errada.

    Os números são os que o OpenAlex REPORTA, não o que é recuperável:
    referenced_works_count conta também IDs que não resolvem mais no próprio
    OpenAlex (works removidos ou mesclados). Ver o rodapé.
    """
    vazio = {"openalex_cited_by_count": None, "openalex_referenced_works_count": None}
    if not doi:
        return vazio

    params = {"mailto": OPENALEX_MAILTO} if OPENALEX_MAILTO else {}
    url = f"https://api.openalex.org/works/https://doi.org/{doi.strip()}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=15) as response:
            work = json.loads(response.read().decode("utf-8"))
    # Qualquer exceção, não só erro HTTP: esta consulta é auxiliar, e uma
    # conexão derrubada no meio de uma rodada de dezenas de minutos não pode
    # interromper a suíte. Sem o dado, as colunas do OpenAlex ficam vazias.
    except Exception as e:
        print(f"    [Aviso OpenAlex] sem dados para {doi}: {e}")
        return vazio

    referenced_works = work.get("referenced_works") or []
    return {
        "openalex_cited_by_count": work.get("cited_by_count"),
        "openalex_referenced_works_count": work.get(
            "referenced_works_count", len(referenced_works)
        ),
    }


def delta(coletado, referencia):
    if coletado is None or referencia is None:
        return None
    return coletado - referencia


def parse_citations_data(data):
    """
    Lê o que a busca de fato coletou, direto dos campos que o pipeline expõe.

    Não usar cadeia de fallbacks aqui: o backward devolve "citations": [] e um
    "citations_count" que é a contagem de citações do artigo semente, vinda da
    API — não algo coletado. Adivinhar a partir dessas chaves fazia o backward
    reportar citações no lugar de referências.

    Devolve um dict com o que foi COLETADO e o que as APIs REPORTAM existir.
    Vazio significa que aquele número não se aplica ou não está disponível.

    Não existe contagem reportada de referências: o referenceCount da Semantic
    Scholar é consultado em search.py mas só vira texto dentro de "warning",
    nunca chega ao JSON como número. Por isso a coluna warning é incluída — é
    onde aparece o caso "a editora bloqueou a lista de referências".
    """
    if not isinstance(data, dict):
        return {}

    return {
        # Um zero legítimo é informação: significa que nada foi coletado, que é
        # justamente a falha que este teste precisa expor. Nunca substituir por
        # um total reportado pela API.
        "citations_retrieved": data.get("citations_retrieved"),
        "references_retrieved": data.get("references_retrieved"),
        # Total que a API atribui ao artigo semente. build_forward grava em
        # "citationCount". A chave "citations_count" vinha do build_backward,
        # já removido; o fallback continua por causa de CSVs antigos.
        "citations_reported": data.get("citationCount", data.get("citations_count")),
        "data_source": data.get("data_source"),
        "resolved_doi": data.get("resolved_doi"),
        "warning": data.get("warning"),
    }


def resultado_vazio(status):
    """Linha de saída quando a execução não produziu JSON utilizável."""
    return {
        "citations_retrieved": None,
        "references_retrieved": None,
        "citations_reported": None,
        "data_source": None,
        "resolved_doi": None,
        "warning": None,
        "status": status,
    }


def run_python_script(script_path, doi, title):
    if not os.path.exists(script_path):
        return resultado_vazio(f"FILE_NOT_FOUND: {script_path}")

    python_executable = sys.executable
    arg_doi = doi if doi else "-"
    arg_title = title if title else "-"

    cmd = [python_executable, "-X", "utf8", script_path, arg_doi, arg_title]

    # Cada artigo entra duas vezes no CSV (título e DOI). Com o cache ligado, a
    # segunda busca lê do disco e devolve o valor da primeira — as duas linhas
    # saem sempre idênticas e o teste não consegue detectar inconsistência
    # nenhuma, que é justamente o que ele existe para medir.
    env = dict(os.environ, SNOWMAP_DISABLE_CACHE="1")

    try:
        completed_process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=SCRIPTS_DIR,
            env=env,
            timeout=TIMEOUT_POR_BUSCA
        )

        if completed_process.returncode == 0:
            stdout_text = completed_process.stdout.strip()

            try:
                data = json.loads(stdout_text)
            except json.JSONDecodeError:
                json_start = stdout_text.find("{")
                json_end = stdout_text.rfind("}")
                if json_start != -1 and json_end != -1:
                    data = json.loads(stdout_text[json_start : json_end + 1])
                else:
                    return resultado_vazio("PARSE_ERROR")

            campos = parse_citations_data(data)
            campos["status"] = "SUCCESS"
            return campos
        else:
            stderr_msg = completed_process.stderr.strip().replace("\n", " ")[:80]
            return resultado_vazio(f"EXEC_ERROR (code {completed_process.returncode}): {stderr_msg}")

    except subprocess.TimeoutExpired:
        return resultado_vazio("TIMEOUT")
    except Exception as e:
        return resultado_vazio(f"ERROR: {str(e)}")


def main():
    print(f"\nLendo artigo(s) em: {INPUT_CSV}")

    papers = load_input_papers(INPUT_CSV)

    if not papers:
        print("(ERRO) Nenhum item válido encontrado no CSV.")
        return

    print(f"Total de linhas lidas no CSV de entrada: {len(papers)}")
    print(f"Total de linhas esperadas na saída: {len(papers) * EXECUCOES_POR_ENTRADA}")

    # "execucao" e não "script"/"direction": as duas linhas de uma entrada são
    # a MESMA busca repetida. É isso que esta suíte mede — se a mesma consulta
    # devolve os mesmos números duas vezes seguidas. Comparar as duas linhas de
    # um artigo com a coluna data_source diz se uma divergência veio do
    # pipeline ou de uma fonte que não respondeu naquela execução.
    fieldnames = [
        "input_title",
        "input_doi",
        "execucao",
        "citations_retrieved",
        "references_retrieved",
        "citations_reported",
        "openalex_cited_by_count",
        "openalex_referenced_works_count",
        "delta_citations_vs_openalex",
        "delta_references_vs_openalex",
        "data_source",
        "resolved_doi",
        "status",
        "warning",
    ]

    def linha(p_title, p_doi, execucao, res, openalex):
        return {
            "input_title": p_title,
            "input_doi": p_doi,
            "execucao": execucao,
            "citations_retrieved": res["citations_retrieved"],
            "references_retrieved": res["references_retrieved"],
            "citations_reported": res["citations_reported"],
            "openalex_cited_by_count": openalex["openalex_cited_by_count"],
            "openalex_referenced_works_count": openalex["openalex_referenced_works_count"],
            "delta_citations_vs_openalex": delta(
                res["citations_retrieved"], openalex["openalex_cited_by_count"]
            ),
            "delta_references_vs_openalex": delta(
                res["references_retrieved"], openalex["openalex_referenced_works_count"]
            ),
            "data_source": res["data_source"],
            "resolved_doi": res["resolved_doi"],
            "status": res["status"],
            "warning": res["warning"],
        }

    # Uma consulta ao OpenAlex por DOI, reaproveitada entre execuções e entre
    # entradas: a linha do título e a linha do DOI de um mesmo artigo resolvem
    # para o mesmo DOI e não precisam pagar duas requisições.
    openalex_por_doi = {}

    total = 0

    # Arquivo aberto antes do laço e cada linha gravada assim que existe. Sem
    # cache a execução leva dezenas de minutos; gravar só no final faria uma
    # interrupção qualquer descartar todas as chamadas já feitas às APIs.
    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        f.flush()

        for idx, paper in enumerate(papers, 1):
            p_title = paper["title"]
            p_doi = paper["doi"]

            identifier = p_doi if p_doi else p_title[:40]
            print(f"\n({idx}/{len(papers)}) Processando linha individual: {identifier}")

            for execucao in range(1, EXECUCOES_POR_ENTRADA + 1):
                print(f"  -> Execução {execucao}/{EXECUCOES_POR_ENTRADA}...")
                res = run_python_script(RUN_FORWARD_PY, doi=p_doi, title=p_title)

                resolved = res.get("resolved_doi")
                doi_referencia = resolved if resolved and resolved != "-" else p_doi
                # DOI não diferencia maiúsculas; o pipeline devolve em minúsculas
                # e a entrada pode vir com maiúsculas ("e-Inf180103").
                chave = (doi_referencia or "").strip().lower()
                if chave not in openalex_por_doi:
                    openalex_por_doi[chave] = fetch_openalex_counts(chave)
                openalex = openalex_por_doi[chave]

                row = linha(p_title, p_doi, execucao, res, openalex)
                writer.writerow(row)
                f.flush()
                total += 1

                print(f"     {res['status']} | citations={res['citations_retrieved']} "
                      f"(openalex {openalex['openalex_cited_by_count']}, "
                      f"delta {row['delta_citations_vs_openalex']}) "
                      f"references={res['references_retrieved']} "
                      f"(openalex {openalex['openalex_referenced_works_count']}, "
                      f"delta {row['delta_references_vs_openalex']}) "
                      f"source={res['data_source']}")

                # A Semantic Scholar limita acesso anônimo a ~1 req/s e cada busca
                # faz de 1 a 3 chamadas. Encadear as execuções sem pausa faz o
                # próprio teste provocar o throttling que ele deveria medir: metade
                # das linhas sai com data_source=openalex por causa do ritmo, não
                # por indisponibilidade real da API.
                time.sleep(PAUSA_ENTRE_BUSCAS)

    print(f"\n(SUCESSO) Processamento concluído! {total} linhas salvas em: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()


"""
Funcionamento da exibição dos dados no CSV de saída (result_searches.csv):

COLETADO (o que o sistema entregou)
- "citations_retrieved": quantas citações a busca trouxe.
- "references_retrieved": quantas referências a busca trouxe.

REPORTADO (o que as APIs dizem existir)
- "citations_reported": total de citações que a API atribui ao artigo semente.

Comparar as duas colunas de citações mostra o quanto ficou pelo caminho. Não há
equivalente para referências: o referenceCount da Semantic Scholar é consultado
em search.py mas só aparece como texto em "warning", nunca como número no JSON.

REFERÊNCIA EXTERNA (OpenAlex consultado direto, fora do pipeline)
- "openalex_cited_by_count": citações que o OpenAlex reporta para o artigo.
- "openalex_referenced_works_count": referências que o OpenAlex LISTA.
- "delta_citations_vs_openalex" e "delta_references_vs_openalex": coletado
  menos OpenAlex.

Os deltas são diferença em relação a uma fonte, não erro do pipeline:
- delta de citações POSITIVO é o esperado quando o Semantic Scholar responde:
  o pipeline soma as fontes e passa do OpenAlex sozinho.
- delta de referências NEGATIVO costuma ser do próprio OpenAlex: o
  referenced_works_count inclui IDs que não resolvem mais (works removidos ou
  mesclados). No 10.1016/j.jss.2021.111044 são 192 listados e cerca de 127
  recuperáveis. A coluna "warning" informa quantos não resolveram.
- Colunas vazias: a busca não devolveu DOI (artigo sem DOI) ou o OpenAlex não
  respondeu. A comparação é feita só pelo DOI resolvido pelo pipeline.

CONTEXTO
- "data_source": openalex ou semantic+openalex. Explica variações entre
  execuções — sem ele não dá para distinguir "o artigo tem poucas citações" de
  "o Semantic Scholar foi barrado nesta rodada".
- "resolved_doi": para conferir se a busca por título resolveu o artigo certo.
- "warning": inclui o caso em que a editora bloqueia a lista de referências.

Todos os números coletados vêm direto dos campos homônimos do JSON, sem
inferência.

Um zero é informação legítima: nada foi coletado. Não é substituído por totais
reportados pelas APIs.

O cache é desligado nos subprocessos (SNOWMAP_DISABLE_CACHE=1), senão a linha do
DOI apenas releria o resultado da linha do título e toda comparação sairia
idêntica.

Variáveis de ambiente opcionais: PAUSA_ENTRE_BUSCAS, TIMEOUT_POR_BUSCA e
OPENALEX_MAILTO (e-mail real para o polite pool do OpenAlex).

ob.: o arquivo de entrada deve ter o nome 'tests_csvs.csv' e estar no mesmo diretório que este script.
"""
