import sys
import json
import traceback
import re
import hashlib
import requests
from semanticscholar import SemanticScholar

def slugify(text):
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text)[:50]

def generate_paper_id(title):
    if not title:
        return "id-desconhecido"
    slug = slugify(title)
    return slug or hashlib.md5(title.encode()).hexdigest()[:10]

def fallback_via_requests(doi):
    fields = "title,year,venue,abstract,authors,citations.title,citations.authors,citations.year,citations.venue,citations.externalIds,citations.abstract"
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields={fields}"
    print(f"[DEBUG] Fallback via API REST: {url}", file=sys.stderr)

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            data["api"] = "semantic"
            return data
        print(f"[DEBUG] Fallback falhou: {response.status_code} - {response.text}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[DEBUG] Erro no fallback: {e}", file=sys.stderr)
        return None

def fallback_openalex(doi):
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    print(f"[DEBUG] OpenAlex: {url}", file=sys.stderr)
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            paper_data = {
                "title": data.get("title", "-"),
                "year": data.get("publication_year", "-"),
                "venue": data.get("host_venue", {}).get("display_name", "-"),
                "abstract": data.get("abstract", "-"),
                "doi": data.get("doi", doi),
                "citations_count": data.get("cited_by_count", 0),
                "citations": [],
                "api": "openalex"
            }
            return paper_data
        print(f"[DEBUG] OpenAlex falhou: {response.status_code} - {response.text}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[DEBUG] Erro no OpenAlex: {e}", file=sys.stderr)
        return None

def search_combined(doi):
    sch = SemanticScholar(timeout=100)
    cleaned_doi = doi.split('doi.org/')[-1].strip()

    # Busca no OpenAlex
    openalex_data = fallback_openalex(cleaned_doi)
    paper_data = fallback_via_requests(cleaned_doi)

    # Se ambos existem e têm mesmo DOI, prioriza OpenAlex.
    if openalex_data and paper_data and openalex_data.get("doi") == paper_data.get("doi"):
        openalex_data['api'] = 'openalex+semantic'
        return openalex_data

    # Se ambos existem mas DOIs diferentes, ainda junta as citações (mais conservador seria alertar)
    elif openalex_data and paper_data:
        openalex_data['citations'] += paper_data.get('citations', [])
        openalex_data['citations_count'] = len(openalex_data['citations'])
        openalex_data['api'] = 'openalex+semantic (doi mismatch)'
        return openalex_data

    # Se só OpenAlex
    elif openalex_data:
        return openalex_data

    # Se só Semantic Scholar
    elif paper_data:
        return paper_data

    else:
        print(json.dumps({"error": f"Artigo com DOI {doi} não encontrado."}))
        sys.exit(1)

def parse_citations(paper):
    citations = []
    for c in paper.get('citations', []):
        title = c.get('title', '-')
        year = c.get('year', '-')
        venue = c.get('venue', '-')
        doi = c.get('externalIds', {}).get('DOI', '-') if 'externalIds' in c else c.get('doi', '-')
        abstract = c.get('abstract', '-')
        authors = c.get('authors', [])
        autores = [{"name": a.get('name', '-')} for a in authors]

        citation_obj = {
            "paperId": generate_paper_id(title),
            "title": title,
            "authors": autores,
            "year": year,
            "venue": venue,
            "doi": doi,
            "abstract": abstract
        }
        citations.append(citation_obj)
    return citations

def contar_citacoes_por_fonte(paper, original_api):
    vistos = set()
    duplicadas = 0

    for c in paper.get('citations', []):
        doi = c.get('doi')
        if not doi:
            continue
        if doi in vistos:
            duplicadas += 1
        else:
            vistos.add(doi)

    total = len(paper.get('citations', []))
    unicos = len(vistos)

    print(f"[INFO] Origem das citações: {original_api}", file=sys.stderr)
    print(f"[INFO] Total de citações extraídas: {total}", file=sys.stderr)
    print(f"[INFO] Citações únicas (sem DOI duplicado): {unicos}", file=sys.stderr)
    print(f"[INFO] Citações duplicadas: {duplicadas}", file=sys.stderr)

def main():
    try:
        if len(sys.argv) < 2:
            print(json.dumps({"error": "Uso: python run_forward.py <DOI>"}))
            sys.exit(1)

        doi = sys.argv[1].strip()
        print(f"[DEBUG] DOI recebido: {doi}", file=sys.stderr)

        paper = search_combined(doi)

        result = {
            "input_doi": paper.get("doi", doi),
            "title": paper.get("title", "-"),
            "year": paper.get("year", "-"),
            "venue": paper.get("venue", "-"),
            "abstract": paper.get("abstract", "-"),
            "citations_count": paper.get("citations_count", len(paper.get("citations", []))),
            "citations": parse_citations(paper)
        }

        citations = parse_citations(paper)
        contar_citacoes_por_fonte({"citations": citations}, paper.get("api", "desconhecida"))


        with open('output.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False, indent=2)) 



    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"error": "Erro inesperado ao processar o artigo."}))
        sys.exit(1)

if __name__ == "__main__":
    main()
