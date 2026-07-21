#!/usr/bin/env python3
"""Standalone SnowMap Analytics POC web application (standard library only)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = os.getenv("SNOWMAP_POC_HOST", "127.0.0.1")
PORT = int(os.getenv("SNOWMAP_POC_PORT", "8890"))
MODEL = os.getenv("SNOWMAP_LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
DB_PATH = Path(tempfile.gettempdir()) / "snowmap_analytics_web.sqlite"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = PROJECT_ROOT / "Framework_snowballing/frontend/images/logo-snowballing.png"
MAX_ROWS = 500

SCHEMA = """papers(paper_id INTEGER, title TEXT, year INTEGER, venue TEXT,
  citation_count INTEGER, open_access INTEGER, screening_status TEXT)
authors(author_id INTEGER, name TEXT, affiliation TEXT)
paper_authors(paper_id INTEGER, author_id INTEGER, author_order INTEGER)
Relacionamentos:
- paper_authors.paper_id -> papers.paper_id
- paper_authors.author_id -> authors.author_id
Semântica:
- open_access: 1 significa acesso aberto e 0 significa fechado
- screening_status: included, excluded ou unsure
- author_order: posição do autor no artigo"""

SQL_SYSTEM = """Você traduz perguntas sobre revisão sistemática para SQLite.
Retorne APENAS JSON válido: {"sql":"...","explanation":"..."}.
Gere exatamente uma consulta SELECT (CTE WITH é permitida), nunca altere dados.
Use aliases curtos, claros e sem espaços. Use CAST(... AS REAL) quando necessário.
Para quantidade de autores por artigo, use paper_authors e COUNT(author_id).
Use somente os nomes exatos: papers, authors e paper_authors. A tabela papers é plural.
Ao usar alias, declare-o no FROM ou JOIN antes de referenciar suas colunas.
Não invente tabelas, aliases nem colunas."""

SQL_SYSTEM += """
Exemplo correto para média de autores por artigo em cada ano:
SELECT p.year AS ano, AVG(t.author_count) AS media_autores
FROM papers AS p
JOIN (SELECT paper_id, COUNT(author_id) AS author_count
      FROM paper_authors GROUP BY paper_id) AS t ON t.paper_id = p.paper_id
GROUP BY p.year ORDER BY p.year
Observe que o alias t expõe author_count, não count."""

CHART_SYSTEM = """Você é especialista em visualização de dados científicos.
Retorne APENAS JSON válido com: chart_type, x, y, title, x_label, y_label.
chart_type deve ser bar, line, scatter, pie ou histogram.
x e y devem ser nomes exatos das colunas fornecidas; y pode ser null apenas para histogram.
Prefira barras para categorias, linha para tempo, scatter para relação numérica e histograma para distribuição."""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|analyze)\b",
    re.I,
)


def create_mock_database() -> None:
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(
        """
        DROP TABLE IF EXISTS paper_authors;
        DROP TABLE IF EXISTS authors;
        DROP TABLE IF EXISTS papers;
        CREATE TABLE papers (
          paper_id INTEGER PRIMARY KEY, title TEXT NOT NULL, year INTEGER NOT NULL,
          venue TEXT NOT NULL, citation_count INTEGER NOT NULL, open_access INTEGER NOT NULL,
          screening_status TEXT NOT NULL
        );
        CREATE TABLE authors (
          author_id INTEGER PRIMARY KEY, name TEXT NOT NULL, affiliation TEXT
        );
        CREATE TABLE paper_authors (
          paper_id INTEGER NOT NULL, author_id INTEGER NOT NULL, author_order INTEGER NOT NULL,
          PRIMARY KEY (paper_id, author_id)
        );
        """
    )
    papers = [
        (1, "Reliable Forward Snowballing", 2021, "EASE", 42, 1, "included"),
        (2, "Automating Study Selection", 2021, "IST", 31, 0, "included"),
        (3, "LLMs for Evidence Synthesis", 2022, "EMSE", 67, 1, "included"),
        (4, "Citation Network Exploration", 2022, "JSS", 24, 1, "excluded"),
        (5, "Human in the Loop Reviews", 2022, "EASE", 18, 0, "unsure"),
        (6, "Open Science Mapping", 2023, "IST", 53, 1, "included"),
        (7, "Visual Analytics for SLRs", 2023, "EMSE", 39, 1, "included"),
        (8, "Reproducible Snowballing", 2023, "JSS", 28, 0, "included"),
        (9, "Prompting for Paper Screening", 2024, "EASE", 21, 1, "unsure"),
        (10, "Knowledge Graphs in Reviews", 2024, "IST", 35, 1, "included"),
        (11, "Evaluating LLM Review Assistants", 2024, "EMSE", 16, 0, "excluded"),
        (12, "Adaptive Literature Discovery", 2025, "JSS", 9, 1, "included"),
    ]
    authors = [
        (1, "Ana Silva", "PUC-Rio"), (2, "Bruno Lima", "USP"),
        (3, "Carla Souza", "UFMG"), (4, "Diego Costa", "UFPE"),
        (5, "Elena Martins", "PUC-Rio"), (6, "Felipe Rocha", "USP"),
        (7, "Giulia Alves", "UFMG"), (8, "Hugo Nunes", "UFPE"),
    ]
    links = [
        (1,1,1),(1,2,2),(2,2,1),(2,3,2),(2,4,3),(3,1,1),(3,3,2),(3,5,3),(3,7,4),
        (4,4,1),(4,6,2),(5,5,1),(5,8,2),(6,1,1),(6,6,2),(6,7,3),(7,2,1),
        (7,5,2),(7,8,3),(8,3,1),(8,4,2),(9,1,1),(9,2,2),(9,5,3),(9,8,4),
        (10,3,1),(10,6,2),(10,7,3),(11,4,1),(11,5,2),(12,1,1),(12,6,2),(12,8,3),
    ]
    connection.executemany("INSERT INTO papers VALUES (?,?,?,?,?,?,?)", papers)
    connection.executemany("INSERT INTO authors VALUES (?,?,?)", authors)
    connection.executemany("INSERT INTO paper_authors VALUES (?,?,?)", links)
    connection.commit()
    connection.close()


def call_ollama(system: str, user: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode()
    request = urllib.request.Request(
        OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)["message"]["content"]
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Não foi possível acessar o Ollama: {exc}") from exc


def extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise ValueError("A LLM não retornou JSON válido.")
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                "A LLM retornou uma resposta estruturada inválida. Tente novamente."
            ) from exc


def validate_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise ValueError("Apenas uma instrução SQL é permitida.")
    if not re.match(r"^(select|with)\b", cleaned, re.I):
        raise ValueError("A consulta deve começar com SELECT ou WITH.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("A consulta contém uma operação não permitida.")
    return cleaned


def execute_query(sql: str) -> tuple[list[str], list[list]]:
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    safe_sql = validate_sql(sql)
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    if hasattr(sqlite3, "SQLITE_RECURSIVE"):
        allowed.add(sqlite3.SQLITE_RECURSIVE)

    def authorizer(action, _arg1, _arg2, _database, _trigger):
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    connection.set_authorizer(authorizer)
    try:
        cursor = connection.execute(f"SELECT * FROM ({safe_sql}) AS result LIMIT {MAX_ROWS}")
        columns = [item[0] for item in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
    finally:
        connection.close()
    return columns, rows


def analyze(question: str) -> dict:
    sql_prompt = f"ESQUEMA DO BANCO:\n{SCHEMA}\n\nPERGUNTA DO USUÁRIO:\n{question}"
    sql_answer = extract_json(call_ollama(SQL_SYSTEM, sql_prompt))
    sql = validate_sql(str(sql_answer.get("sql", "")))
    corrected = False
    last_error = None
    for attempt in range(4):
        try:
            columns, rows = execute_query(sql)
            break
        except sqlite3.Error as query_error:
            last_error = query_error
            if attempt == 3:
                raise
            repair_prompt = f"""A consulta abaixo falhou no SQLite.
ESQUEMA DO BANCO:
{SCHEMA}

PERGUNTA ORIGINAL:
{question}

SQL QUE FALHOU:
{sql}

ERRO DO SQLITE:
{query_error}

Corrija a consulta usando apenas o esquema fornecido. Confira cada alias e cada coluna
antes de responder. Não repita a consulta que falhou."""
            sql_answer = extract_json(call_ollama(SQL_SYSTEM, repair_prompt))
            sql = validate_sql(str(sql_answer.get("sql", "")))
            corrected = True
    if not rows:
        raise ValueError("A consulta não retornou dados.")
    samples = [dict(zip(columns, row)) for row in rows[:5]]
    chart_prompt = (
        f"Pergunta: {question}\nColunas exatas: {json.dumps(columns, ensure_ascii=False)}"
        f"\nAmostra: {json.dumps(samples, ensure_ascii=False)}"
    )
    chart = extract_json(call_ollama(CHART_SYSTEM, chart_prompt))
    if chart.get("chart_type") not in {"bar", "line", "scatter", "pie", "histogram"}:
        raise ValueError("A LLM escolheu um tipo de gráfico não permitido.")
    if chart.get("x") not in columns or (chart.get("y") is not None and chart.get("y") not in columns):
        raise ValueError("A LLM escolheu colunas inexistentes para o gráfico.")
    return {
        "question": question,
        "sql": sql,
        "explanation": sql_answer.get("explanation", ""),
        "sql_corrected": corrected,
        "columns": columns,
        "rows": rows,
        "chart": chart,
        "model": MODEL,
    }


HTML = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SnowMap Analytics POC</title>
<style>
:root{--green:#1f7a4d;--dark:#1f3d35;--mint:#eaf7ef;--line:#d8eee1;--text:#171717}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--text);font:14px 'Poppins',Arial,sans-serif}
header{height:72px;background:var(--mint);border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 max(28px,calc((100vw - 1380px)/2));gap:12px;position:sticky;top:0;z-index:10}
.logo{height:28px;width:auto}.brand{font-size:18px;font-weight:600;color:#000}.nav-links{margin-left:auto;display:flex;gap:28px;color:var(--dark);font-weight:500}.nav-active{color:#0b6b43}
main{max-width:1380px;margin:52px auto;padding:0 32px}.hero{background:var(--mint);border-radius:1.8rem;padding:34px 36px}
.hero h2{font-size:30px;font-weight:600;margin:0 0 10px}.hero p{margin:0;color:#53645e;max-width:780px;line-height:1.6}
.ask{display:flex;gap:12px;margin-top:24px}textarea{flex:1;min-height:82px;border:1px solid #d5d5d5;border-radius:.9rem;padding:15px 18px;font:inherit;resize:vertical;outline:none;background:#fff}textarea:focus{border-color:var(--green);box-shadow:0 0 0 3px #1f7a4d18}button{border:0;border-radius:999px;padding:0 24px;background:var(--green);color:white;font:500 14px 'Poppins',sans-serif;cursor:pointer}button:hover{background:#17633f}button:disabled{opacity:.6;cursor:wait}
.examples{display:flex;flex-wrap:wrap;gap:9px;margin:18px 0 0}.chip{background:transparent;border:1px solid var(--green);color:var(--dark);padding:7px 13px;border-radius:999px;font-size:12px;font-weight:500}.chip:hover{background:#d8eee1}
.status{display:none;margin:20px 0;padding:14px 17px;border-radius:10px;background:white;border:1px solid var(--line)}.status.show{display:block}.error{color:#a42c2c;background:#fff0f0;border-color:#f3c4c4}
.grid{display:grid;grid-template-columns:1.4fr .9fr;gap:24px;margin-top:28px}.card{background:var(--mint);border:0;border-radius:1.8rem;padding:30px}.card h3{margin:0 0 18px;font-size:20px;font-weight:500}.hidden{display:none}
.chart-wrap{height:390px;position:relative}canvas{width:100%;height:100%}.actions{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.download{background:var(--green);color:white;padding:9px 13px}
pre{background:#fff;color:#243c35;padding:16px;border:1px solid #d5e6da;border-radius:.9rem;white-space:pre-wrap;overflow:auto;font-size:13px}.explain{line-height:1.6;color:#53645e}
.table-wrap{overflow:auto;max-height:360px;background:#fff;border-radius:1rem}table{border-collapse:collapse;width:100%;font-size:13px}th{position:sticky;top:0;background:#d8eee1;color:var(--dark)}th,td{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line);white-space:nowrap}
.meta{font-size:12px;color:#718285;margin-top:12px}@media(max-width:800px){.grid{grid-template-columns:1fr}.ask{flex-direction:column}button{height:48px}}
</style></head><body>
<header><img class="logo" src="/images/logo-snowballing.png" alt="SnowMap"><span class="brand">SnowMap</span><nav class="nav-links"><span class="nav-active">Data Analysis</span><span>Criteria Applications</span></nav></header>
<main><section class="hero"><h2>Explore your research data</h2><p>Describe the analysis you need and generate a custom visualization using the articles from your review.</p>
<div class="ask"><textarea id="question">Show the average number of authors per article in each year.</textarea><button id="generate">Generate chart</button></div>
<div class="examples"><button class="chip">Articles by venue</button><button class="chip">Average citations by access type</button><button class="chip">Five most cited authors</button><button class="chip">Included articles by year</button></div></section>
<div id="status" class="status"></div>
<section id="results" class="hidden"><div class="grid"><article class="card"><div class="actions"><h3 id="chart-title">Visualization</h3><button class="download" id="download">Download PNG</button></div><div class="chart-wrap"><canvas id="chart"></canvas></div></article>
<aside class="card"><h3>Generated query</h3><pre id="sql"></pre><p id="explanation" class="explain"></p><div id="meta" class="meta"></div></aside></div>
<article class="card" style="margin-top:24px"><h3>Chart data</h3><div class="table-wrap"><table id="data-table"></table></div></article></section></main>
<script>
const $=s=>document.querySelector(s), statusEl=$('#status'), results=$('#results'), canvas=$('#chart');
document.querySelectorAll('.chip').forEach(b=>b.onclick=()=>{$('#question').value=b.textContent+'.'});
function status(text,error=false){statusEl.textContent=text;statusEl.className='status show'+(error?' error':'')}
function table(data){const t=$('#data-table');t.textContent='';const h=document.createElement('tr');data.columns.forEach(c=>{const th=document.createElement('th');th.textContent=c;h.appendChild(th)});const thead=document.createElement('thead');thead.appendChild(h);t.appendChild(thead);const body=document.createElement('tbody');data.rows.forEach(row=>{const tr=document.createElement('tr');row.forEach(v=>{const td=document.createElement('td');td.textContent=v??'';tr.appendChild(td)});body.appendChild(tr)});t.appendChild(body)}
function draw(data){const spec=data.chart, xi=data.columns.indexOf(spec.x), yi=data.columns.indexOf(spec.y);const dpr=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*dpr;canvas.height=h*dpr;const c=canvas.getContext('2d');c.scale(dpr,dpr);c.clearRect(0,0,w,h);c.font='12px Arial';c.fillStyle='#44585c';const pad={l:62,r:22,t:25,b:72};const W=w-pad.l-pad.r,H=h-pad.t-pad.b;let points=data.rows.map(r=>({x:r[xi],y:yi>=0?Number(r[yi]):Number(r[xi])}));
if(spec.chart_type==='histogram'){const vals=points.map(p=>p.y),bins=Math.min(10,Math.max(3,Math.ceil(Math.sqrt(vals.length)))),min=Math.min(...vals),max=Math.max(...vals),step=(max-min||1)/bins,counts=Array(bins).fill(0);vals.forEach(v=>counts[Math.min(bins-1,Math.floor((v-min)/step))]++);points=counts.map((y,i)=>({x:(min+i*step).toFixed(1),y}))}
if(spec.chart_type==='pie'){const total=points.reduce((s,p)=>s+p.y,0);let a=-Math.PI/2;const colors=['#176d6d','#4ba39a','#f0c75e','#6e8fa7','#b77d9d','#89ad6a'];points.forEach((p,i)=>{const n=a+(p.y/total)*Math.PI*2;c.beginPath();c.moveTo(w*.43,h*.49);c.arc(w*.43,h*.49,Math.min(W,H)*.36,a,n);c.fillStyle=colors[i%colors.length];c.fill();c.fillRect(w*.72,45+i*25,12,12);c.fillStyle='#34484c';c.fillText(String(p.x),w*.72+18,56+i*25);a=n});return}
const max=Math.max(...points.map(p=>p.y),1)*1.12;c.strokeStyle='#dce8e6';c.fillStyle='#607477';for(let i=0;i<=5;i++){const y=pad.t+H-i*H/5;c.beginPath();c.moveTo(pad.l,y);c.lineTo(w-pad.r,y);c.stroke();c.fillText((max*i/5).toFixed(max<10?1:0),8,y+4)}
const xPos=i=>pad.l+(i+.5)*W/points.length,yPos=v=>pad.t+H-(v/max)*H;c.strokeStyle='#176d6d';c.fillStyle='#176d6d';
if(spec.chart_type==='line'){c.beginPath();points.forEach((p,i)=>i?c.lineTo(xPos(i),yPos(p.y)):c.moveTo(xPos(i),yPos(p.y)));c.lineWidth=3;c.stroke();points.forEach((p,i)=>{c.beginPath();c.arc(xPos(i),yPos(p.y),4,0,Math.PI*2);c.fill()})}
else if(spec.chart_type==='scatter'){points.forEach((p,i)=>{c.beginPath();c.arc(xPos(i),yPos(p.y),6,0,Math.PI*2);c.fill()})}
else{const bw=Math.max(8,W/points.length*.58);points.forEach((p,i)=>c.fillRect(xPos(i)-bw/2,yPos(p.y),bw,pad.t+H-yPos(p.y)))}
c.fillStyle='#52676a';points.forEach((p,i)=>{c.save();c.translate(xPos(i),pad.t+H+12);c.rotate(-.45);c.fillText(String(p.x).slice(0,22),0,0);c.restore()});c.save();c.translate(15,pad.t+H/2);c.rotate(-Math.PI/2);c.fillText(spec.y_label||'',0,0);c.restore()}
$('#generate').onclick=async()=>{const q=$('#question').value.trim();if(!q)return;$('#generate').disabled=true;results.className='hidden';status('Preparing your visualization...');try{const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});const d=await r.json();if(!r.ok)throw Error(d.error||'Analysis failed');$('#sql').textContent=d.sql;$('#explanation').textContent=d.explanation;$('#meta').textContent=`${d.rows.length} result row(s)`;$('#chart-title').textContent=d.chart.title;table(d);results.className='';status('Visualization generated successfully.');requestAnimationFrame(()=>draw(d))}catch(e){status(e.message,true)}finally{$('#generate').disabled=false}};
$('#download').onclick=()=>{const a=document.createElement('a');a.download='snowmap-analytics.png';a.href=canvas.toDataURL('image/png');a.click()};window.onresize=()=>{if(!results.classList.contains('hidden'))$('#generate').click()};
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self.send_json(200, {"status": "ok", "model": MODEL})
            return
        if self.path == "/images/logo-snowballing.png" and LOGO_PATH.is_file():
            body = LOGO_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path not in {"/", "/index.html"}:
            self.send_error(404)
            return
        body = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/analyze":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            question = str(payload.get("question", "")).strip()
            if not question or len(question) > 1000:
                raise ValueError("Informe uma pergunta com até 1000 caracteres.")
            self.send_json(200, analyze(question))
        except (ValueError, RuntimeError, sqlite3.Error, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"error": f"Erro inesperado: {exc}"})

    def log_message(self, fmt: str, *args) -> None:
        print(f"[SnowMap POC] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    create_mock_database()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SnowMap Analytics POC: http://{HOST}:{PORT}")
    print(f"Ollama: {OLLAMA_URL} | modelo: {MODEL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
