# EdgeIQ — Sports Intelligence Platform

> The Intelligent Edge. A multi-sport same-game parlay intelligence platform built
> on verified last-N floor data, live enrichment, and a self-improving agent loop.

EdgeIQ does not speculate. Every recommendation is grounded in **floor-verified
statistical baselines** — the worst-case last-N performance a player has actually
delivered — never season averages or projections. See
[`Docs/EdgeIQ_SRS_Design_v1.docx`](Docs/EdgeIQ_SRS_Design_v1.docx) for the full SRS.

---

## What's built so far (v1.0 foundation)

The heart of the system — the **Floor Model engine** and the agent chain around
it — is implemented, tested, and runnable end to end against a sample feed.

| Layer | Status | Where |
|-------|--------|-------|
| Sport Router + multi-sport config (10 sports, NBA/NFL active) | ✅ | [`app/sports/registry.py`](backend/app/sports/registry.py) |
| **Floor Model engine** (9 absolute rules, fully tested) | ✅ | [`app/floor/engine.py`](backend/app/floor/engine.py) |
| Confidence Scorer (6 weighted factors) | ✅ | [`app/scoring/confidence.py`](backend/app/scoring/confidence.py) |
| Kelly Sizer (fractional Kelly + stake caps) | ✅ | [`app/scoring/kelly.py`](backend/app/scoring/kelly.py) |
| SGP Builder (negative-correlation guard, NO-BET rule) | ✅ | [`app/parlay/builder.py`](backend/app/parlay/builder.py) |
| Result Grader (CLV computation) | ✅ | [`app/grading.py`](backend/app/grading.py) |
| Pipeline (Router → Floor → Score → Size → Build) | ✅ | [`app/pipeline.py`](backend/app/pipeline.py) |
| FastAPI REST API (SRS §06 routes) | ✅ | [`app/api/routes.py`](backend/app/api/routes.py) |
| Feed provider abstraction + circuit breaker (SRS §01) | ✅ | [`app/feeds/`](backend/app/feeds/) |
| **SportRadar adapter** (real NBA v8 game logs) | ✅ | [`app/feeds/sportradar.py`](backend/app/feeds/sportradar.py) |
| **Next.js dashboard** (Agent Feed, Parlay Builder, Model Health) | ✅ | [`frontend/src/`](frontend/src/) |
| Enrichment layer (Perplexity / Reddit) | ⏳ | `EnrichmentContext` modeled; agents stubbed |
| Odds feed (OddsJam / FanDuel lines) | ⏳ | `OddsBook` interface + `StaticOddsBook` bridge |
| Stream processing (Kafka / TimescaleDB / Redis) | ⏳ | `docker-compose.yml` provisions stores |
| Obsidian second brain + learning loop | ⏳ | grader writes modeled; vault adapter pending |
| Shadow Tester | ⏳ | route returns `pending_data` |

The floor model enforces every absolute rule from SRS §04/§08 — incomplete
samples, single-game misses, ceiling props, injury flags, lines above the
average, and floors that don't clear the line are all rejected, and a parlay is
**never forced** below 8 qualifying legs.

---

## Quick start (backend)

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Run the tests (floor model rules + pipeline + API)
.venv/bin/pytest -q

# Start the API
.venv/bin/uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

### Try it

```bash
# Floor-verified picks for a sport
curl localhost:8000/api/picks/nba

# Build the same-game parlay (8 legs or NO BET)
curl -X POST localhost:8000/api/parlay/build \
  -H 'Content-Type: application/json' -d '{"sport":"nba"}'

# NFL sample intentionally returns NO BET (only 3 legs pass the floor model)
curl -X POST localhost:8000/api/parlay/build \
  -H 'Content-Type: application/json' -d '{"sport":"nfl"}'
```

## Frontend (Next.js dashboard)

```bash
cd frontend
npm install
npm run dev   # → http://localhost:3000  (expects the API on :8000)
```

The dashboard renders the SRS §07 views: the **Agent Feed** (live floor-verified
picks with floor/line gap bars, confidence badges, and enrichment flags), the
**Parlay Builder** (8-leg SGP or an explicit NO BET), and **Model Health**
(circuit-breaker status per feed). Set `NEXT_PUBLIC_API_URL` to point at a
non-local backend.

## Switching to the live SportRadar feed

The backend defaults to the bundled sample feed. To pull real NBA game logs:

```bash
export EDGEIQ_FEED_PROVIDER=sportradar
export EDGEIQ_SPORTRADAR_API_KEY=your_nba_key   # else it degrades back to sample
```

The adapter assembles each player's last-N game logs from SportRadar's
`summary.json` endpoint (walking recent daily schedules), and prices them against
operator-supplied lines in [`backend/data/lines.json`](backend/data/lines.json)
— SportRadar provides stats, not odds, so you paste the lines from your book
there (keyed by player name) until the OddsJam/FanDuel feed is wired. Responses
are disk-cached and rate-limit-aware (429 backoff) for the trial tier.

Every feed call runs under a circuit breaker; an outage or stale data trips it
and hard-stops downstream agents (SRS §01), surfaced at `/api/feed/health`.

## Local infrastructure

```bash
docker compose up -d   # Postgres, TimescaleDB, Redis (SRS §03/§06)
```

---

## Architecture (SRS §03 — Six-Layer Stack)

```
Layer 1  Data Ingestion      circuit-breaker watchdog on every feed
Layer 2  Context Enrichment  Perplexity (facts) + Reddit (sentiment)
Layer 3  Stream Processing   Kafka → Redis cache → TimescaleDB
Layer 4  AI Agent Layer      8 Claude agents (Router…Shadow Tester)
Layer 5  Obsidian Second Brain   persistent learning loop
Layer 6  Frontend            Next.js live dashboard
```

Data flows top-to-bottom; **learning flows bottom-to-top** through the Obsidian
loop. The longer EdgeIQ runs, the sharper it gets.

## Repo layout

```
backend/
  app/
    sports/      sport router + per-sport config (sample window, stat schema)
    floor/       the Floor Model engine — the foundation of the system
    scoring/     confidence scorer + Kelly sizer
    parlay/      SGP builder with correlation guard
    models/      shared Pydantic domain models
    api/         FastAPI routes (SRS §06)
    pipeline.py  the agent chain wired end to end
    grading.py   Result Grader + CLV
  tests/         floor-model rule tests + pipeline/API tests
Docs/            SRS & system design document
docker-compose.yml
```

## Roadmap

- **v1.0** (Q3 2026) — NBA + NFL floor model, FanDuel/DK odds, basic Obsidian loop *(foundation built)*
- **v1.1** (Q4 2026) — MLB + NHL, correlation matrix live, Reddit enrichment
- **v1.2** (Q4 2026) — Kelly sizer live, CLV grader, shadow tester, Perplexity
- **v2.0** (Q1 2027) — all 10 sports, public % feed, reverse line movement detector

---

_Confidential — internal. Not betting advice; gamble responsibly._
