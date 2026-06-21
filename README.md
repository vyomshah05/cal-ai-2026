# Lockstep

[Live Site](https://vyomshah05.github.io/lockstep/)

Lockstep is an MCP server that hands coding agents (Claude Code, Devin, etc.)
accurate, version-pinned library docs so they stop hallucinating APIs. It
exposes four MCP tools — `plan_task`, `resolve_version`, `recommend_library`,
`get_versioned_docs` — backed by a Supabase + pgvector library/function
corpus and a Redis W-TinyLFU semantic cache.

## Layout

| Path | What |
|---|---|
| `server.py` | MCP server entrypoint (stdio / streamable-http) |
| `tools/` | The four MCP tool implementations |
| `config.py`, `cache.py`, `redis_client.py`, `supabase_client.py`, `embeddings.py` | Core server plumbing |
| `librariesintodatabase/` | Scraper pipeline that populates the Supabase corpus (`scrape.py`, `db.py`, `schema.sql`) |
| `webapp/` | React dashboard — setup guides + a form to add your own library docs |
| `webapp_api/` | FastAPI backend behind the dashboard's "Add your documentation" form; thin wrapper over `librariesintodatabase/db.py` |
| `webhook.py` | Sentry → Lockstep remediation webhook |
| `CONTRACT.md` | Source of truth for the Supabase/Redis schema |

## Quick start (MCP server)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, REDIS_*, ANTHROPIC_API_KEY
python -m server
```

See the dashboard's **Claude Code** and **Devin** pages (run `webapp/`, below)
for client-specific wiring, or `.devin/DEVIN_SETUP.md` directly.

## Quick start (web dashboard)

```bash
# backend
pip install -e .                      # fastapi/uvicorn already in pyproject.toml
python -m webapp_api.main             # http://localhost:8002

# frontend, in a second terminal
cd webapp
npm install
npm run dev                           # http://localhost:5173
```

## Adding library documentation

Either run the scraper pipeline in `librariesintodatabase/` (`python scrape.py`),
or use the dashboard's **Add your documentation** form, which calls the same
`db.py` upsert functions through `webapp_api`.
