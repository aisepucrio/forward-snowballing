# Framework Snowballing

## Overview

**Framework Snowballing** (SnowMap) is a hybrid web application designed to perform
systematic literature reviews using snowballing techniques. It combines a Node.js/Express
backend with Python scripts for citation analysis and LLM-based screening.

Access the deployed version of the framework here: https://snowmap.aise-lab.com/

## Key Features

- **Citation Analysis**: Forward and Backward citation tracking using multiple APIs
- **LLM Integration**: Automated screening through [OpenRouter](https://openrouter.ai)
- **Persistence**: PostgreSQL for searches, papers and screening flags
- **API Aggregation**: Support for multiple citation databases:
  - OpenAlex
  - Semantic Scholar
  - Crossref
- **Web Interface**: HTML/CSS frontend for configuration and result visualization

## Repository Structure

```
Framework_snowballing/
├── frontend/             # HTML/CSS/JS user interface
├── controllers/          # Express route handlers
├── routes/               # API route definitions
├── services/             # Session management, Python runner, search service
├── server/               # Application bootstrap
├── scripts/              # Python: citation analysis, LLM processing, database
├── init/                 # SQL executed when the Postgres container is first created
├── docker-compose.yml    # PostgreSQL container
├── package.json          # Node.js dependencies
├── requirements.txt      # Python dependencies
└── README.md
```

---

## Requirements

| Component | Required? | Used for |
|---|---|---|
| Node.js 14+ and npm | **Yes** | Web server and interface |
| Python 3.8+ | **Yes** | Citation search and analysis |
| Docker | No | PostgreSQL database |
| OpenRouter API key | No | LLM-based screening |

Only Node and Python are mandatory. Without Docker the application runs and searches
normally — results simply are not persisted to PostgreSQL. Without an OpenRouter key,
every step works except the automated criteria screening.

---

## Installation

All commands below are run from the `Framework_snowballing` directory.

### 1. Node dependencies

```bash
npm install
```

### 2. Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file in `Framework_snowballing/` with the variables below:

| Variable | Default | Notes |
|---|---|---|
| `DB_HOST` | `localhost` | |
| `DB_PORT` | `5433` | Must match the host port in `docker-compose.yml` |
| `DB_NAME` | `snowmap_bd` | |
| `DB_USER` | `postgres` | |
| `DB_PASSWORD` | `postgres` | |
| `TEMP_USER_ID` | `00000000-0000-0000-0000-000000000001` | Fixed user until login exists |
| `SEMANTIC_API_KEY` | — | Optional. Raises Semantic Scholar rate limits |
| `PORT` | `3000` | Web server port |
| `OPENROUTER_API_KEY` | — | Required for LLM screening. Server-side only |
| `LLM_MODEL` | `openai/gpt-4o` | Any OpenRouter model that supports structured outputs |
| `LLM_FALLBACK_MODELS` | — | Optional, comma-separated OpenRouter models tried when the main one fails. Each must accept the same parameters (reasoning, and the JSON schema when enabled) |
| `GEMINI_API_KEY` | — | Optional. When OpenRouter fails, screening falls back to the Google Gemini API directly |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Fallback chain, comma-separated and tried in order (e.g. `gemini-3.7-flash,gemini-3.5-flash-lite`). Put the model with the larger free quota last |
| `LLM_MAX_WORKERS` | `8` | Parallel LLM calls (one call per article, with all criteria) |
| `LLM_TEMPERATURE` | `0` | |
| `LLM_MAX_TOKENS` | `1000` | Upper bound per call. OpenRouter reserves credit for it; raise it for reasoning models |
| `LLM_STRUCTURED_OUTPUT` | `true` | Sends the JSON schema. Set `false` for models without `structured_outputs` (e.g. most `:free` variants) |
| `LLM_REASONING` | `false` | Enables reasoning (`reasoning: {enabled: true}`) |
| `LLM_REASONING_EFFORT` | — | Optional: `low`, `medium` or `high` instead of the default effort |
| `LLM_TIMEOUT_SECONDS` | `120` | Per call; 408/429/5xx are retried up to 3 times |

`.env` is git-ignored and must never be committed.

### 4. Database (optional)

The database stores searches, papers, authors and screening flags. **The application runs
without it** — you will see `[BD INDISPONIVEL]` in the terminal and nothing is persisted.

To enable it:

```bash
docker compose up -d
```

This creates a PostgreSQL 18 container and runs the scripts in `init/`, which build the
schema and insert the fixed user. It only takes effect the first time the volume is
created.

Verify:

```bash
docker compose ps
```

```bash
docker compose exec db psql -U postgres -d snowmap_bd -c "\dt"
```

Eight tables should be listed: `criteria`, `criteria_logs`, `paper_authors`, `papers`,
`search_results`, `searches`, `users`, `venues`.

Everyday commands:

| Task | Command |
|---|---|
| Start | `docker compose up -d` |
| Stop (keeps data) | `docker compose stop` |
| Status | `docker compose ps` |
| Logs | `docker compose logs db` |
| SQL shell | `docker compose exec db psql -U postgres -d snowmap_bd` |
| Reset from scratch | `docker compose down -v` then `docker compose up -d` |

> **Changing the schema later:** the files in `init/` only run when the volume is created
> from scratch — adding a new `.sql` there has no effect on an existing database. The
> workflow is to apply the change in the container, regenerate `init/01-schema.sql` with
> `pg_dump --schema-only --no-owner --no-privileges`, commit it, and have the team run
> `docker compose down -v && docker compose up -d`. Note that schema changes usually
> require matching changes in `scripts/services/snowmap_bd.py`, which lists columns
> explicitly in its SQL.

### 5. OpenRouter (optional)

Required only for the automated screening on the Criteria page. Create a key at
<https://openrouter.ai/settings/keys> and set `OPENROUTER_API_KEY` in `.env`. The model
and all LLM parameters are configured only in `.env`; the interface never sends them.
Token usage and cost of each call are printed to the server log as `[LLM USAGE]`.

The screening prompt, response schema and selection rule live in
`scripts/services/prompt.py`. The evaluation tools in `LLMs_Analysis/` run through this
same module and through `scripts/analisys_LLM.py`, so they measure what the application
actually does.

---

## Running

```bash
npm start
```

Available at `http://localhost:3000`.

For auto-reload during development:

```bash
npm run dev
```

---

## Usage

1. Enter the **DOI or title** of the seed article and click **Search**.
2. The results table shows **Cited By** (forward). Switch to **References** (backward)
   using the toggle in the navigation bar.
3. Mark articles with **Include** / **Exclude**, use **Remove Duplicates** to review
   near-identical entries, and **Export** to download a CSV.
4. Go to **Criteria Applications** to define inclusion and exclusion criteria and run the
   LLM screening over the selected articles.

---

## Troubleshooting

**`[BD INDISPONIVEL]` in the terminal**
The `psycopg2` driver is not installed, or the database is not running. Run
`pip install -r requirements.txt` and `docker compose up -d`. Harmless if you do not need
persistence.

**`[ERRO CRITICO BD]` in the terminal**
The driver is installed but the connection failed. Check that `DB_PORT` in `.env` matches
the host port published in `docker-compose.yml`, and that `docker compose ps` shows
`healthy`.

**`port is already allocated` when starting the container**
Another PostgreSQL is using the port. Change `DB_PORT` in `.env` and restart the
container.

**Search returns an error**
The external APIs (OpenAlex, Semantic Scholar, Crossref) impose rate limits. Setting
`SEMANTIC_API_KEY` reduces throttling. Results are cached in `cache/snowballing_cache.db`,
so repeating a search is fast.

**LLM screening fails with `OpenRouter recusou a requisicao`**
HTTP 401 means an invalid `OPENROUTER_API_KEY`, 402 means no credits left, and 404 usually
means `LLM_MODEL` does not exist or does not support structured outputs.

---

## License

See `LICENSE` file in the repository root.
