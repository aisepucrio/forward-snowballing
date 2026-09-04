import os
import csv
import json
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

FRAMEWORK_DIR = os.path.dirname(SCRIPT_DIR)

SCRIPTS_DIR = os.path.join(FRAMEWORK_DIR, "scripts")

RUN_FORWARD_PY = os.path.join(SCRIPTS_DIR, "run_forward.py")
RUN_BACKWARD_PY = os.path.join(SCRIPTS_DIR, "run_backward.py")

INPUT_CSV = os.path.join(SCRIPT_DIR, "tests_csvs.csv")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "result_searches.csv")


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
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip():
                continue
            
            line_content = row[0].strip()

            if line_content.lower() in ["title", "doi", "input_title", "input_doi"]:
                continue

            if line_content.startswith("10.") or "/" in line_content and not " " in line_content:
                papers.append({"title": "", "doi": line_content})
            else:
                papers.append({"title": line_content, "doi": ""})

    return papers


def parse_citations_data(data):
    if not isinstance(data, dict):
        return 0, 0

    citations_list = []
    list_keys = ["citations", "references", "results", "data", "papers"]
    
    for key in list_keys:
        if key in data and isinstance(data[key], list):
            citations_list = data[key]
            break

    length_citations = len(citations_list)
    citations_count = data.get("citations_count", data.get("references_count", data.get("total", None)))

    if citations_count is None or citations_count == 0:
        citations_count = length_citations

    if length_citations == 0 and citations_count > 0:
        length_citations = citations_count

    return citations_count, length_citations


def run_python_script(script_path, doi, title):
    if not os.path.exists(script_path):
        return {
            "status": f"FILE_NOT_FOUND: {script_path}",
            "citations_count": None,
            "length_citations": None
        }

    python_executable = sys.executable
    arg_doi = doi if doi else "-"
    arg_title = title if title else "-"

    cmd = [python_executable, "-X", "utf8", script_path, arg_doi, arg_title]

    try:
        completed_process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=SCRIPTS_DIR,
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
                    return {
                        "status": "PARSE_ERROR",
                        "citations_count": None,
                        "length_citations": None
                    }

            citations_count, length_citations = parse_citations_data(data)

            return {
                "status": "SUCCESS",
                "citations_count": citations_count,
                "length_citations": length_citations
            }
        else:
            stderr_msg = completed_process.stderr.strip().replace("\n", " ")[:80]
            return {
                "status": f"EXEC_ERROR (code {completed_process.returncode}): {stderr_msg}",
                "citations_count": None,
                "length_citations": None
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "citations_count": None,
            "length_citations": None
        }
    except Exception as e:
        return {
            "status": f"ERROR: {str(e)}",
            "citations_count": None,
            "length_citations": None
        }


def main():
    print(f"\nLendo artigo(s) em: {INPUT_CSV}")
    
    papers = load_input_papers(INPUT_CSV)
    
    if not papers:
        print("(ERRO) Nenhum item válido encontrado no CSV.")
        return

    print(f"Total de linhas lidas no CSV de entrada: {len(papers)}")
    print(f"Total de linhas esperadas na saída (2x): {len(papers) * 2}")

    fieldnames = [
        "input_title",
        "input_doi",
        "direction",
        "citations_count",
        "length_citations",
        "status"
    ]

    results = []

    for idx, paper in enumerate(papers, 1):
        p_title = paper["title"]
        p_doi = paper["doi"]
        
        identifier = p_doi if p_doi else p_title[:40]
        print(f"\n({idx}/{len(papers)}) Processando linha individual: {identifier}")

        print("  -> Executando Forward...")
        fwd_res = run_python_script(RUN_FORWARD_PY, doi=p_doi, title=p_title)
        results.append({
            "input_title": p_title,
            "input_doi": p_doi,
            "direction": "forward",
            "citations_count": fwd_res["citations_count"],
            "length_citations": fwd_res["length_citations"],
            "status": fwd_res["status"]
        })

        print("  -> Executando Backward...")
        bwd_res = run_python_script(RUN_BACKWARD_PY, doi=p_doi, title=p_title)
        results.append({
            "input_title": p_title,
            "input_doi": p_doi,
            "direction": "backward",
            "citations_count": bwd_res["citations_count"],
            "length_citations": bwd_res["length_citations"],
            "status": bwd_res["status"]
        })

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=",")
        writer.writeheader()
        writer.writerows(results)

    print(f"\n(SUCESSO) Processamento concluído! {len(results)} linhas salvas em: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()


"""
Funcionamento da exibição dos dados no CSV de saída (result_searches.csv):

- no forward: a coluna "citations_count" mostra o número de referências.
- no backward: a coluna "citations_count" mostra o número de citações.
- a coluna "length_citations" mostra sempre o número de citações.

ob.: o arquivo de entrada deve ter o nome 'tests_csvs.csv' e estar no mesmo diretório que este script.
"""