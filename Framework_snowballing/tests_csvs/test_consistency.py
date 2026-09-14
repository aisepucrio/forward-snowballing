import os
import csv
import json
import subprocess
import sys
import time
import urllib.request
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK_DIR = os.path.dirname(SCRIPT_DIR)
SCRIPTS_DIR = os.path.join(FRAMEWORK_DIR, "scripts")

RUN_FORWARD_PY = os.path.join(SCRIPTS_DIR, "run_forward.py")

INPUT_CSV = os.path.join(SCRIPT_DIR, "tests_csvs.csv")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "result_searches.csv")

EXECUCOES_POR_ENTRADA = 2
PAUSA_ENTRE_BUSCAS = float(os.getenv("PAUSA_ENTRE_BUSCAS", "2"))
TIMEOUT_POR_BUSCA = float(os.getenv("TIMEOUT_POR_BUSCA", "300"))


def fetch_openalex_data(doi_or_title):
    """
    Consulta diretamente a API pública do OpenAlex para obter os dados oficiais
    de citações (cited_by_count) e referências (referenced_works_count).
    """
    if not doi_or_title or doi_or_title == "-":
        return {"openalex_citations": None, "openalex_references": None}

    headers = {'User-Agent': 'SnowmapTester/1.0 (mailto:test@snowmap.org)'}

    try:
        if doi_or_title.startswith("10.") or ("/" in doi_or_title and " " not in doi_or_title):
            url = f"https://api.openalex.org/works/https://doi.org/{doi_or_title.strip()}"
        else:
            query = urllib.parse.quote(doi_or_title.strip())
            url = f"https://api.openalex.org/works?filter=title.search:{query}"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                
                if "results" in data:
                    if not data["results"]:
                        return {"openalex_citations": None, "openalex_references": None}
                    work = data["results"][0]
                else:
                    work = data

                cited_by = work.get("cited_by_count")
                referenced_works = work.get("referenced_works", [])
                referenced_count = work.get("referenced_works_count", len(referenced_works))

                return {
                    "openalex_citations": cited_by,
                    "openalex_references": referenced_count
                }
    except Exception as e:
        print(f"    [Aviso OpenAlex API] Não foi possível obter dados diretos: {e}")

    return {"openalex_citations": None, "openalex_references": None}


def load_input_papers(csv_path):
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

            if line_content.startswith("10.") or "/" in line_content and " " not in line_content:
                papers.append({"title": "", "doi": line_content})
            else:
                papers.append({"title": line_content, "doi": ""})

    return papers


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

    print(f"Total de linhas lidas no CSV de entrada: {len(papers)}")
    print(f"Total de linhas esperadas na saída: {len(papers) * EXECUCOES_POR_ENTRADA}")

    fieldnames = [
        "input_title",
        "input_doi",
        "execucao",
        "citations_retrieved",
        "references_retrieved",
        "citations_reported",
        "openalex_citations",
        "openalex_references",
        "diff_citations",
        "diff_references",
        "data_source",
        "resolved_doi",
        "status",
        "warning",
    ]

    total = 0

    # f.flush() força a gravação imediata no disco usando o manipulador do arquivo f
    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        f.flush()

        for idx, paper in enumerate(papers, 1):
            p_title = paper["title"]
            p_doi = paper["doi"]

            identifier = p_doi if p_doi else p_title
            print(f"\n({idx}/{len(papers)}) Processando: {identifier[:50]}...")

            openalex_info = fetch_openalex_data(p_doi if p_doi else p_title)

            for execucao in range(1, EXECUCOES_POR_ENTRADA + 1):
                print(f"  -> Execução {execucao}/{EXECUCOES_POR_ENTRADA}...")
                res = run_python_script(RUN_FORWARD_PY, doi=p_doi, title=p_title)
                
                c_retrieved = res.get("citations_retrieved")
                r_retrieved = res.get("references_retrieved")
                oa_cit = openalex_info.get("openalex_citations")
                oa_ref = openalex_info.get("openalex_references")

                diff_cit = (c_retrieved - oa_cit) if (c_retrieved is not None and oa_cit is not None) else None
                diff_ref = (r_retrieved - oa_ref) if (r_retrieved is not None and oa_ref is not None) else None

                linha = {
                    "input_title": p_title,
                    "input_doi": p_doi,
                    "execucao": execucao,
                    "citations_retrieved": c_retrieved,
                    "references_retrieved": r_retrieved,
                    "citations_reported": res["citations_reported"],
                    "openalex_citations": oa_cit,
                    "openalex_references": oa_ref,
                    "diff_citations": diff_cit,
                    "diff_references": diff_ref,
                    "data_source": res["data_source"],
                    "resolved_doi": res["resolved_doi"],
                    "status": res["status"],
                    "warning": res["warning"],
                }

                writer.writerow(linha)
                f.flush()
                total += 1

                print(f"     {res['status']} | Citations: script={c_retrieved} vs openalex={oa_cit} (diff={diff_cit}) | "
                      f"References: script={r_retrieved} vs openalex={oa_ref} (diff={diff_ref})")

                time.sleep(PAUSA_ENTRE_BUSCAS)

    print(f"\n(SUCESSO) Processamento concluído! {total} linhas salvas em: {OUTPUT_CSV}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[AVISO] Execução interrompida manualmente. Os dados parciais foram salvos em result_searches.csv.")
        sys.exit(0)