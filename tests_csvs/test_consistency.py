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

EXECUCOES_POR_ENTRADA = 2

INPUT_CSV = os.path.join(SCRIPT_DIR, "tests_csvs.csv")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "result_searches.csv")
VALORES_REAIS_CSV = os.path.join(SCRIPT_DIR, "valores_reais_artigos.csv")

PAUSA_ENTRE_BUSCAS = float(os.getenv("PAUSA_ENTRE_BUSCAS", "2"))
TIMEOUT_POR_BUSCA = float(os.getenv("TIMEOUT_POR_BUSCA", "300"))

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


def load_valores_reais(csv_path):
    """
    Lê o CSV contendo os valores reais de artigos.
    Retorna dois dicionários indexados por DOI em minúsculas e por Título em minúsculas
    mapeando para o valor de 'Backward Real do Artigo'.
    """
    reais_por_doi = {}
    reais_por_titulo = {}

    if not os.path.exists(csv_path):
        print(f"(AVISO) Arquivo de valores reais não encontrado em: {csv_path}")
        return reais_por_doi, reais_por_titulo

    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doi = (row.get("DOI") or "").strip().lower()
            titulo = (row.get("Título") or row.get("Titulo") or "").strip().lower()
            val_raw = row.get("Backward Real do Artigo") or row.get("Backward Real")

            if val_raw is not None and val_raw != "":
                try:
                    val = int(val_raw)
                    if doi:
                        reais_por_doi[doi] = val
                    if titulo:
                        reais_por_titulo[titulo] = val
                except ValueError:
                    pass

    return reais_por_doi, reais_por_titulo


def get_valor_real(p_title, p_doi, resolved_doi, reais_por_doi, reais_por_titulo):
    """
    Busca o valor real do artigo utilizando a prioridade:
    1. DOI resolvido pelo pipeline
    2. DOI informado no arquivo de entrada
    3. Título do artigo
    """
    # 1. Tenta pelo resolved_doi
    if resolved_doi and resolved_doi != "-":
        chave_doi = resolved_doi.strip().lower()
        if chave_doi in reais_por_doi:
            return reais_por_doi[chave_doi]

    # 2. Tenta pelo DOI de entrada
    if p_doi:
        chave_doi = p_doi.strip().lower()
        if chave_doi in reais_por_doi:
            return reais_por_doi[chave_doi]

    # 3. Tenta pelo Título
    if p_title:
        chave_title = p_title.strip().lower()
        if chave_title in reais_por_titulo:
            return reais_por_titulo[chave_title]

    return None


def fetch_openalex_counts(doi):
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
    if not isinstance(data, dict):
        return {}

    return {
        "citations_retrieved": data.get("citations_retrieved"),
        "references_retrieved": data.get("references_retrieved"),
        "citations_reported": data.get("citationCount", data.get("citations_count")),
        "data_source": data.get("data_source"),
        "resolved_doi": data.get("resolved_doi"),
        "warning": data.get("warning"),
    }


def resultado_vazio(status):
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

    # Carrega a tabela com os valores reais dos artigos
    reais_por_doi, reais_por_titulo = load_valores_reais(VALORES_REAIS_CSV)

    print(f"Total de linhas lidas no CSV de entrada: {len(papers)}")
    print(f"Total de linhas esperadas na saída: {len(papers) * EXECUCOES_POR_ENTRADA}")

    fieldnames = [
        "input_title",
        "input_doi",
        "execucao",
        "citations_retrieved",
        "references_retrieved",
        "backward_real",
        "delta_references_vs_real",
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

    def linha(p_title, p_doi, execucao, res, openalex, backward_real):
        return {
            "input_title": p_title,
            "input_doi": p_doi,
            "execucao": execucao,
            "citations_retrieved": res["citations_retrieved"],
            "references_retrieved": res["references_retrieved"],
            "backward_real": backward_real,
            "delta_references_vs_real": delta(
                res["references_retrieved"], backward_real
            ),
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

    openalex_por_doi = {}

    total = 0

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
                chave = (doi_referencia or "").strip().lower()
                
                if chave not in openalex_por_doi:
                    openalex_por_doi[chave] = fetch_openalex_counts(chave)
                openalex = openalex_por_doi[chave]

                # Obtém o valor real de referência do artigo
                b_real = get_valor_real(p_title, p_doi, resolved, reais_por_doi, reais_por_titulo)

                row = linha(p_title, p_doi, execucao, res, openalex, b_real)
                writer.writerow(row)
                f.flush()
                total += 1

                print(f"     {res['status']} | citations={res['citations_retrieved']} "
                      f"references={res['references_retrieved']} "
                      f"(real={b_real}, delta_real={row['delta_references_vs_real']}) "
                      f"source={res['data_source']}")

                time.sleep(PAUSA_ENTRE_BUSCAS)

    print(f"\n(SUCESSO) Processamento concluído! {total} linhas salvas em: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()