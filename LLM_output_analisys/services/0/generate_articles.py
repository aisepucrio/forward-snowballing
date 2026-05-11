import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_JSON_PATH = BASE_DIR / "articles.json"



def carregar_json_base(path: Path) -> dict:
    texto = path.read_text(encoding="utf-8-sig").strip()
    data = json.loads(texto) if texto else {}
    data["artigos"] = []
    return data


def limpar_texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def carregar_artigos_do_csv(path: Path) -> list[dict]:
    artigos = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        linhas = list(reader)

    if len(linhas) < 1:
        return artigos

    cabecalho = linhas[0]
    dados = linhas[1:]

    try:
        idx_title = cabecalho.index("Title")
        idx_abstract = cabecalho.index("Abstract")
    except ValueError as e:
        raise ValueError(
            f"Colunas nao encontradas. Cabecalho lido: {cabecalho}"
        ) from e

    for linha in dados:
        if len(linha) <= max(idx_title, idx_abstract):
            continue

        title = limpar_texto(linha[idx_title])
        abstract = limpar_texto(linha[idx_abstract])

        if not title and not abstract:
            continue

        artigos.append({
            "title": title,
            "abstract": abstract
        })

    return artigos


def gerar_artigos(IC_EC_path, BASE_path):
    data = carregar_json_base(Path(BASE_DIR / IC_EC_path))
    data["artigos"] = carregar_artigos_do_csv(Path(BASE_DIR / BASE_path))

    OUTPUT_JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    gerar_artigos("IC_EC.json", "source.csv")
