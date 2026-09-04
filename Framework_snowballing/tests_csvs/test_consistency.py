import os
import csv
import json
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FRAMEWORK_DIR = os.path.dirname(SCRIPT_DIR)

SCRIPTS_DIR = os.path.join(FRAMEWORK_DIR, "scripts")

RUN_FORWARD_PY = os.path.join(SCRIPTS_DIR, "run_forward.py")
RUN_BACKWARD_PY = os.path.join(SCRIPTS_DIR, "run_backward.py")

INPUT_CSV = os.path.join(SCRIPT_DIR, "tests_csvs.csv")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "result_searches.csv")

# Segundos de espera após cada busca, para não estourar o limite anônimo da
# Semantic Scholar (~1 req/s). Ajustável por variável de ambiente.
PAUSA_ENTRE_BUSCAS = float(os.getenv("PAUSA_ENTRE_BUSCAS", "2"))


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

            if line_content.startswith("10.") or "/" in line_content and not " " in line_content:
                papers.append({"title": "", "doi": line_content})
            else:
                papers.append({"title": line_content, "doi": ""})

    return papers


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
        # "citationCount" e build_backward em "citations_count" — mesma coisa,
        # nomes diferentes.
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
            timeout=120
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
    print(f"Total de linhas esperadas na saída (2x): {len(papers) * 2}")

    # "script" e não "direction": desde que o pipeline foi unificado, run_forward
    # devolve citações E referências, então a linha do run_backward não traz
    # nenhum número que a do forward já não tenha. As duas entradas continuam
    # úteis como execuções independentes — servem para flagrar variação entre
    # chamadas — mas o que a coluna distingue é qual script rodou, não qual
    # direção foi medida.
    fieldnames = [
        "input_title",
        "input_doi",
        "script",
        "citations_retrieved",
        "references_retrieved",
        "citations_reported",
        "data_source",
        "resolved_doi",
        "status",
        "warning",
    ]

    def linha(p_title, p_doi, script, res):
        return {
            "input_title": p_title,
            "input_doi": p_doi,
            "script": script,
            "citations_retrieved": res["citations_retrieved"],
            "references_retrieved": res["references_retrieved"],
            "citations_reported": res["citations_reported"],
            "data_source": res["data_source"],
            "resolved_doi": res["resolved_doi"],
            "status": res["status"],
            "warning": res["warning"],
        }

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

            for script, caminho in (("run_forward", RUN_FORWARD_PY),
                                    ("run_backward", RUN_BACKWARD_PY)):
                print(f"  -> Executando {script}...")
                res = run_python_script(caminho, doi=p_doi, title=p_title)
                writer.writerow(linha(p_title, p_doi, script, res))
                f.flush()
                total += 1

                print(f"     {res['status']} | citations={res['citations_retrieved']} "
                      f"references={res['references_retrieved']} source={res['data_source']}")

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

CONTEXTO
- "data_source": openalex ou semantic+openalex. Explica variações entre
  execuções — sem ele não dá para distinguir "o artigo tem poucas citações" de
  "o Semantic Scholar foi barrado nesta rodada".
- "resolved_doi": para conferir se a busca por título resolveu o artigo certo.
- "warning": inclui o caso em que a editora bloqueia a lista de referências.

Todos os números vêm direto dos campos homônimos do JSON, sem inferência. Vazio
significa que o número não se aplica — run_backward não coleta citações.

Um zero é informação legítima: nada foi coletado. Não é substituído por totais
reportados pelas APIs.

O cache é desligado nos subprocessos (SNOWMAP_DISABLE_CACHE=1), senão a linha do
DOI apenas releria o resultado da linha do título e toda comparação sairia
idêntica.

ob.: o arquivo de entrada deve ter o nome 'tests_csvs.csv' e estar no mesmo diretório que este script.
"""