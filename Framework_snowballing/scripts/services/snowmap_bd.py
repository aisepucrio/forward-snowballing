import os
import sys
import json
import uuid
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    """Retorna uma conexão com o banco PostgreSQL."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "snowmap_bd"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


# ---------------------------------- PAPERS ----------------------------------

def _coerce_year(value):
    """
    Converte year pra int ou None.

    Os provedores de busca (services/search.py) usam "-" como placeholder
    quando o ano de publicação não é conhecido — bem comum em dados reais de
    citação. year é uma coluna `integer` em papers, então inserir a string
    "-" direto quebra o INSERT (invalid input syntax for type integer).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def save_paper(doi=None, title=None, year=None, abstract=None,
               citation_count=0, semantic_paper_id=None,
               openalex_id=None, venue_id=None):
    """
    Insere um paper no banco se ele ainda não existir.
    Verifica duplicata por DOI, semantic_paper_id ou título.
    Retorna o id (UUID) do paper — seja o já existente ou o recém-criado.
    """
    year = _coerce_year(year)

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # 1. tenta achar pelo DOI
        if doi:
            cursor.execute("SELECT id FROM papers WHERE doi = %s", (doi,))
            row = cursor.fetchone()
            if row:
                print("[DB SKIP - DOI JÁ EXISTE]", file=sys.stderr)
                return str(row["id"])

        # 2. tenta achar pelo semantic_paper_id
        if semantic_paper_id:
            cursor.execute(
                "SELECT id FROM papers WHERE semantic_paper_id = %s",
                (semantic_paper_id,)
            )
            row = cursor.fetchone()
            if row:
                print("[DB SKIP - SEMANTIC ID JÁ EXISTE]", file=sys.stderr)
                return str(row["id"])

        # 3. tenta achar pelo título (case-insensitive)
        if title:
            cursor.execute(
                "SELECT id FROM papers WHERE LOWER(title) = LOWER(%s)",
                (title,)
            )
            row = cursor.fetchone()
            if row:
                print("[DB SKIP - TÍTULO JÁ EXISTE]", file=sys.stderr)
                return str(row["id"])

        # 4. insere se não existir
        paper_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO papers
                (id, doi, semantic_paper_id, openalex_id, title,
                 year, abstract, citation_count, venue_id)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            paper_id, doi, semantic_paper_id, openalex_id,
            title, year, abstract, citation_count, venue_id
        ))

        conn.commit()
        print("[DB SAVE - PAPER]", file=sys.stderr)
        return paper_id

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - save_paper] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


def save_authors(paper_id, authors: list):
    """
    Insere os autores de um paper.
    authors deve ser uma lista de dicts: [{"name": "Fulano"}, ...]
    """
    if not authors:
        return

    conn = get_connection()
    cursor = conn.cursor()

    try:
        for order, author in enumerate(authors, start=1):
            cursor.execute("""
                INSERT INTO paper_authors (id, paper_id, name, author_order)
                VALUES (%s, %s, %s, %s)
            """, (str(uuid.uuid4()), paper_id, author.get("name"), order))

        conn.commit()
        print(f"[DB SAVE - {len(authors)} AUTORES]", file=sys.stderr)

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - save_authors] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


def get_paper_by_doi(doi):
    """Busca um paper pelo DOI. Retorna dict ou None."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT * FROM papers WHERE doi = %s", (doi,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        cursor.close()
        conn.close()


def get_paper_by_title(title):
    """Busca um paper pelo título (case-insensitive). Retorna dict ou None."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            "SELECT * FROM papers WHERE LOWER(title) = LOWER(%s)", (title,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        cursor.close()
        conn.close()


# ---------------------------------- SEARCHES ----------------------------------

def create_search(seed_paper_id, created_by, direction, data_source=None):
    """
    Registra uma execução de snowballing.
    direction: 'forward' ou 'backward'
    Retorna o id (UUID) da search criada.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        search_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO searches
                (id, seed_paper_id, created_by, direction, data_source)
            VALUES
                (%s, %s, %s, %s, %s)
        """, (search_id, seed_paper_id, created_by, direction, data_source))

        conn.commit()
        print(f"[DB SAVE - SEARCH {direction.upper()}]", file=sys.stderr)
        return search_id

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - create_search] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


def get_search(search_id):
    """Retorna os dados de uma busca pelo id."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT * FROM searches WHERE id = %s", (search_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        cursor.close()
        conn.close()


# ---------------------------------- SEARCH RESULTS ----------------------------------

def save_search_result(search_id, paper_id,
                       selected_first_page=False,
                       excluded_duplicate=False,
                       duplicate_of=None):
    """
    Vincula um paper a uma busca com suas flags.
    Se o par (search_id, paper_id) já existir, ignora.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO search_results
                (id, search_id, paper_id,
                 selected_first_page, excluded_duplicate, duplicate_of)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (search_id, paper_id) DO NOTHING
        """, (
            str(uuid.uuid4()), search_id, paper_id,
            selected_first_page, excluded_duplicate, duplicate_of
        ))

        conn.commit()
        print("[DB SAVE - SEARCH RESULT]", file=sys.stderr)

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - save_search_result] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()

def _apply_result_flags(cursor, search_id, paper_id,
                        selected_first_page=None,
                        excluded_duplicate=None,
                        duplicate_of=None):
    """
    Aplica as flags de um resultado já existente usando um cursor já aberto.
    Só atualiza os campos que forem passados (não None).
    Não faz commit/rollback nem fecha nada — quem chama controla a transação.
    Retorna True se um UPDATE foi executado, False se foi pulado (paper_id
    não resolvido ou nenhum campo para atualizar).
    """
    try:
        uuid.UUID(str(paper_id))
    except ValueError:
        cursor.execute("""
            SELECT id FROM papers
            WHERE semantic_paper_id = %s OR doi = %s
        """, (paper_id, paper_id))
        row = cursor.fetchone()
        if row:
            paper_id = str(row[0])
        else:
            print(f"[DB WARN - update_result_flags] ID inválido e paper não encontrado: {paper_id}", file=sys.stderr)
            return False

    fields = []
    values = []

    if selected_first_page is not None:
        fields.append("selected_first_page = %s")
        values.append(selected_first_page)

    if excluded_duplicate is not None:
        fields.append("excluded_duplicate = %s")
        values.append(excluded_duplicate)

    if duplicate_of is not None:
        fields.append("duplicate_of = %s")
        values.append(duplicate_of)

    if not fields:
        return False

    fields.append("updated_at = NOW()")
    values.extend([search_id, paper_id])

    cursor.execute(f"""
        UPDATE search_results
        SET {', '.join(fields)}
        WHERE search_id = %s AND paper_id = %s
    """, values)

    return True


def update_result_flags(search_id, paper_id,
                        selected_first_page=None,
                        excluded_duplicate=None,
                        duplicate_of=None):
    """
    Atualiza as flags de um único resultado já existente (uma conexão por chamada).
    Mantido para compatibilidade com update_flag.py; a triagem em lote usa
    update_result_flags_batch, que reaproveita uma única conexão para vários itens.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        _apply_result_flags(cursor, search_id, paper_id,
                             selected_first_page=selected_first_page,
                             excluded_duplicate=excluded_duplicate,
                             duplicate_of=duplicate_of)

        conn.commit()
        print("[DB UPDATE - FLAGS]", file=sys.stderr)

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - update_result_flags] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


def update_result_flags_batch(updates):
    """
    Aplica várias atualizações de flags numa única conexão/transação.
    `updates` é uma lista de dicts com search_id, paper_id, e opcionalmente
    selected_first_page, excluded_duplicate, duplicate_of.
    Itens com paper_id não resolvido são pulados (não abortam o lote inteiro).
    Retorna (updated_count, skipped_paper_ids).
    """
    conn = get_connection()
    cursor = conn.cursor()

    updated_count = 0
    skipped = []

    try:
        for item in updates:
            search_id = item.get("search_id")
            paper_id = item.get("paper_id")

            if not search_id or not paper_id:
                skipped.append(paper_id)
                continue

            applied = _apply_result_flags(
                cursor, search_id, paper_id,
                selected_first_page=item.get("selected_first_page"),
                excluded_duplicate=item.get("excluded_duplicate"),
                duplicate_of=item.get("duplicate_of"),
            )

            if applied:
                updated_count += 1
            else:
                skipped.append(paper_id)

        conn.commit()
        print(f"[DB UPDATE - FLAGS BATCH] {updated_count} atualizados, {len(skipped)} pulados", file=sys.stderr)

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - update_result_flags_batch] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()

    return updated_count, skipped

def get_search_results(search_id, only_selected=False, exclude_duplicates=True):
    """
    Retorna todos os papers de uma busca com seus dados completos.
    only_selected=True  → só os marcados na primeira página
    exclude_duplicates=True → remove os marcados como duplicata
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
            SELECT
                sr.id            AS result_id,
                sr.selected_first_page,
                sr.excluded_duplicate,
                sr.duplicate_of,
                sr.updated_at,
                p.id             AS paper_id,
                p.doi,
                p.title,
                p.year,
                p.abstract,
                p.citation_count,
                p.semantic_paper_id,
                p.openalex_id
            FROM search_results sr
            JOIN papers p ON p.id = sr.paper_id
            WHERE sr.search_id = %s
        """
        params = [search_id]

        if only_selected:
            query += " AND sr.selected_first_page = TRUE"

        if exclude_duplicates:
            query += " AND sr.excluded_duplicate = FALSE"

        query += " ORDER BY p.year DESC, p.title ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    finally:
        cursor.close()
        conn.close()


# ---------------------------------- CRITERIA ----------------------------------

def save_criterion(search_id, description, criterion_type):
    """
    Salva um critério de inclusão ou exclusão para uma busca.
    criterion_type: 'inclusion' ou 'exclusion'
    Retorna o id do critério criado.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        criterion_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO criteria (id, search_id, description, type)
            VALUES (%s, %s, %s, %s)
        """, (criterion_id, search_id, description, criterion_type))

        conn.commit()
        print(f"[DB SAVE - CRITERION {criterion_type.upper()}]", file=sys.stderr)
        return criterion_id

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - save_criterion] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


def get_criteria(search_id, criterion_type=None):
    """
    Retorna os critérios de uma busca.
    criterion_type: 'inclusion', 'exclusion' ou None (retorna todos)
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        if criterion_type:
            cursor.execute("""
                SELECT * FROM criteria
                WHERE search_id = %s AND type = %s
                ORDER BY type, id
            """, (search_id, criterion_type))
        else:
            cursor.execute("""
                SELECT * FROM criteria
                WHERE search_id = %s
                ORDER BY type, id
            """, (search_id,))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    finally:
        cursor.close()
        conn.close()


# ---------------------------------- CRITERIA LOGS ----------------------------------

def save_criteria_log(paper_id, criteria_id, passed, reason=None):
    """
    Registra se um paper passou ou não em um critério.
    Se o par (paper_id, criteria_id) já existir, atualiza.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO criteria_logs
                (id, paper_id, criteria_id, passed, reason)
            VALUES
                (%s, %s, %s, %s, %s)
            ON CONFLICT (paper_id, criteria_id)
            DO UPDATE SET
                passed       = EXCLUDED.passed,
                reason       = EXCLUDED.reason,
                evaluated_at = NOW()
        """, (str(uuid.uuid4()), paper_id, criteria_id, passed, reason))

        conn.commit()
        status = "PASSOU" if passed else "REPROVADO"
        print(f"[DB SAVE - CRITERIA LOG {status}]", file=sys.stderr)

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - save_criteria_log] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()


def _resolve_paper_id_by_identity(cursor, doi=None, title=None):
    """
    Acha o id de um paper já salvo, por DOI ou (se não achar) por título
    case-insensitive — mesma lógica de dedupe que save_paper() já usa.
    Retorna None se não encontrar.
    """
    if doi and doi != "-":
        cursor.execute("SELECT id FROM papers WHERE doi = %s", (doi,))
        row = cursor.fetchone()
        if row:
            return str(row[0])

    if title and title != "-":
        cursor.execute("SELECT id FROM papers WHERE LOWER(title) = LOWER(%s)", (title,))
        row = cursor.fetchone()
        if row:
            return str(row[0])

    return None


def _get_or_create_criterion(cursor, search_id, description, criterion_type):
    """
    Reaproveita o critério se (search_id, type, description) já existir —
    evita duplicar linhas em `criteria` toda vez que a análise é rerodada
    com o mesmo texto de critério.
    """
    cursor.execute("""
        SELECT id FROM criteria
        WHERE search_id = %s AND type = %s AND description = %s
    """, (search_id, criterion_type, description))
    row = cursor.fetchone()
    if row:
        return str(row[0])

    criterion_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO criteria (id, search_id, description, type)
        VALUES (%s, %s, %s, %s)
    """, (criterion_id, search_id, description, criterion_type))
    return criterion_id


def save_criteria_and_logs(search_id, criteria, results):
    """
    Grava os critérios de inclusão/exclusão de uma busca e o veredito da LLM
    para cada (paper, critério), numa única conexão/transação — pensado pro
    fim da análise em criterios.html, uma chamada só em vez de uma por artigo.

    criteria: {"Inclusion": {"IC1": "desc", ...}, "Exclusion": {"EC1": "desc", ...}}
              (mesmo formato que services/prompt.py:criteria_from_text produz)
    results:  [{"doi": ..., "title": ..., "results": {"IC1": "Yes", ...}}, ...]

    O paper de cada item é resolvido por doi/título (o paper já foi salvo na
    busca original). Itens sem paper correspondente são pulados, não abortam
    o lote inteiro. "passed" = True só quando a LLM respondeu "Yes"; a
    resposta bruta (No/Unsure/error) fica em `reason`.

    Retorna {criteria_saved, logs_saved, skipped_papers}.
    """
    conn = get_connection()
    cursor = conn.cursor()

    criteria_saved = 0
    logs_saved = 0
    skipped_papers = []

    try:
        criterion_ids = {}  # ex.: "IC1" -> uuid do banco

        for criterion_type, group in (
            ("inclusion", (criteria or {}).get("Inclusion") or {}),
            ("exclusion", (criteria or {}).get("Exclusion") or {}),
        ):
            for label, description in group.items():
                criterion_ids[label] = _get_or_create_criterion(
                    cursor, search_id, description, criterion_type
                )
                criteria_saved += 1

        for item in (results or []):
            doi = item.get("doi")
            title = item.get("title")
            paper_id = _resolve_paper_id_by_identity(cursor, doi=doi, title=title)

            if not paper_id:
                print(f"[DB WARN - save_criteria_and_logs] Paper não encontrado: doi={doi} title={title}", file=sys.stderr)
                skipped_papers.append(doi or title)
                continue

            for label, raw_answer in (item.get("results") or {}).items():
                criterion_id = criterion_ids.get(label)
                if not criterion_id:
                    continue

                passed = str(raw_answer or "").strip().lower() == "yes"

                cursor.execute("""
                    INSERT INTO criteria_logs (id, paper_id, criteria_id, passed, reason)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (paper_id, criteria_id)
                    DO UPDATE SET
                        passed       = EXCLUDED.passed,
                        reason       = EXCLUDED.reason,
                        evaluated_at = NOW()
                """, (str(uuid.uuid4()), paper_id, criterion_id, passed, raw_answer))
                logs_saved += 1

        conn.commit()
        print(
            f"[DB SAVE - CRITERIA ANALYSIS] {criteria_saved} critérios, "
            f"{logs_saved} logs, {len(skipped_papers)} artigos pulados",
            file=sys.stderr
        )

    except Exception as e:
        conn.rollback()
        print(f"[DB ERROR - save_criteria_and_logs] {e}", file=sys.stderr)
        raise
    finally:
        cursor.close()
        conn.close()

    return {
        "criteria_saved": criteria_saved,
        "logs_saved": logs_saved,
        "skipped_papers": skipped_papers,
    }


def get_criteria_logs(search_id, paper_id=None):
    """
    Retorna os logs de avaliação de critérios de uma busca.
    Se paper_id for passado, filtra só os logs daquele paper.
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
            SELECT
                cl.id,
                cl.passed,
                cl.reason,
                cl.evaluated_at,
                p.title      AS paper_title,
                p.doi        AS paper_doi,
                c.description AS criterion_description,
                c.type        AS criterion_type
            FROM criteria_logs cl
            JOIN papers   p ON p.id = cl.paper_id
            JOIN criteria c ON c.id = cl.criteria_id
            WHERE c.search_id = %s
        """
        params = [search_id]

        if paper_id:
            query += " AND cl.paper_id = %s"
            params.append(paper_id)

        query += " ORDER BY c.type, p.title"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    finally:
        cursor.close()
        conn.close()


# ---------------------------------- UTILITÁRIO — salva tudo de uma vez a partir do JSON de output ----------------------------------

def save_full_result(output_json: dict, user_id: str):
    """
    Recebe o output_json gerado pelo backend (run_forward.py / run_backward.py)
    e salva tudo no banco: seed, citations/references, autores e search_results.

    Espera a estrutura:
    {
      "input_doi": "...",
      "input_title": "...",
      "title": "...",
      "authors": [...],
      "year": ...,
      "venue": "...",
      "abstract": "...",
      "citationCount": ...,
      "data_source": "...",
      "mode": "forward" | "backward",
      "citations": [ { paperId, title, doi, authors, year, ... }, ... ]
    }
    """

    direction = output_json.get("mode", "forward")
    data_source = output_json.get("data_source")

    # 1. salva o seed
    seed_id = save_paper(
        doi=output_json.get("resolved_doi") or output_json.get("input_doi"),
        title=output_json.get("title"),
        year=output_json.get("year"),
        abstract=output_json.get("abstract"),
        citation_count=output_json.get("citationCount", 0),
    )

    seed_authors = output_json.get("authors", [])
    if seed_authors:
        save_authors(seed_id, seed_authors)

    # 2. cria a search
    search_id = create_search(
        seed_paper_id=seed_id,
        created_by=user_id,
        direction=direction,
        data_source=data_source,
    )

    # 3. salva cada citação/referência
    paper_id_map = {}

    citations = output_json.get("citations", [])
    skipped_items = 0
    for item in citations:
        # Um item com dado ruim (ex.: year mal-formado, texto gigante) não pode
        # derrubar a busca inteira — cada citação/referência é independente.
        try:
            paper_id = save_paper(
                doi=item.get("doi"),
                title=item.get("title"),
                year=item.get("year"),
                abstract=item.get("abstract"),
                citation_count=item.get("citationCount", 0),
                semantic_paper_id=item.get("paperId"),
            )

            item_authors = item.get("authors", [])
            if item_authors:
                save_authors(paper_id, item_authors)

            save_search_result(
                search_id=search_id,
                paper_id=paper_id,
                selected_first_page=False,
                excluded_duplicate=False,
            )

            key = item.get("paperId") or item.get("doi")
            if key:
                paper_id_map[key] = paper_id

        except Exception as item_error:
            skipped_items += 1
            print(
                f"[DB ERROR - save_full_result item] {item_error} | title={item.get('title')}",
                file=sys.stderr
            )
            continue

    print(
        f"[DB SAVE COMPLETO] seed={seed_id} | search={search_id} "
        f"| {len(citations) - skipped_items}/{len(citations)} resultados salvos"
        f"{f' ({skipped_items} pulados por erro)' if skipped_items else ''}",
        file=sys.stderr
    )

    return {
        "seed_id": seed_id,
        "search_id": search_id,
        "paper_id_map": paper_id_map
    }