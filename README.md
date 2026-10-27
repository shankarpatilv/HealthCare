# HealthCare Plans API (FastAPI)

A healthcare plan CRUD API. Plans are JSON documents validated against a JSON Schema
(`app/schemas/plan.schema.json`) and stored in **Redis**, both as a whole-plan document and as
per-object keys (plan, cost shares, plan services, services). Responses carry strong **ETags**
for conditional reads (`If-None-Match`) and conditional writes (`If-Match`). All endpoints
require a **Google OAuth bearer token** (an ID token JWT verified against Google's JWKS, or an
opaque access token checked via Google's tokeninfo endpoint). Every create/update/delete publishes
an event to **RabbitMQ**; a separate **indexer worker** consumes those events and syncs the plan
and its children into **Elasticsearch** (parent/child join).

## Architecture

```
client ──▶ FastAPI (auth · schema validation · ETags) ──▶ Redis (source of truth)
                     │
                     └─ plan events ──▶ RabbitMQ ──▶ indexer worker ──▶ Elasticsearch
```

## Endpoints

All routes are under `/api/v1/plans` and require `Authorization: Bearer <token>`.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check (`{"ok": true}`), no auth |
| `POST` | `/api/v1/plans` | Create a plan (schema-validated). `201` + `ETag`; `409` if `objectId` exists |
| `GET` | `/api/v1/plans` | List all stored plans |
| `GET` | `/api/v1/plans/{id}` | Get a plan with `ETag`; `304` if `If-None-Match` matches; `404` if missing |
| `PUT` | `/api/v1/plans/{id}` | Full replace (schema-validated). Body `objectId` must match URL (`400`); `412` on `If-Match` mismatch |
| `PATCH` | `/api/v1/plans/{id}` | Partial update via smart merge; merged result re-validated (`400`); `412` on `If-Match` mismatch |
| `DELETE` | `/api/v1/plans/{id}` | Delete the plan and its per-object keys. `204`; `404` if missing |

## Project structure

```
app/
├── main.py              # FastAPI app, /health, router + error handlers
├── server.py            # uvicorn entry point
├── config.py            # environment configuration
├── middleware/
│   ├── auth.py          # Google bearer token verification (dependency)
│   ├── validation.py    # JSON Schema validation of plan bodies
│   └── error_handler.py # uniform {"error": ...} responses
├── routes/
│   └── plans_routes.py  # /api/v1/plans CRUD + conditional requests
├── schemas/
│   └── plan.schema.json # plan JSON Schema
├── services/
│   ├── redis.py         # Redis client + key helpers
│   ├── plan_store.py    # store/delete plan graph in Redis
│   ├── etag.py          # canonical JSON + SHA-256 ETags
│   ├── queue.py         # RabbitMQ publisher for plan events
│   └── elasticsearch.py # Elasticsearch client
├── utils/
│   └── merge.py         # objectId-aware merge used by PATCH
└── workers/
    └── plan_indexer.py  # RabbitMQ consumer -> Elasticsearch indexer
tests/                   # pytest suite
```

## Configuration

Copy `.env.example` to `.env` (loaded with python-dotenv).

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8080` | API port |
| `REDIS_URL` | `redis://127.0.0.1:6379` | Redis connection URL |
| `NODE_ENV` | `development` | Environment name (`development` enables reload; `test` silences error logs) |
| `RABBITMQ_URL` | `amqp://localhost` | RabbitMQ connection URL |
| `RABBITMQ_QUEUE` | `plan-events` | Queue for plan events |
| `ELASTIC_URL` | `http://localhost:9200` | Elasticsearch URL |
| `ELASTIC_INDEX` | `demo` | Elasticsearch index name |

## Running

Requires Python 3.10+, plus Redis, RabbitMQ and Elasticsearch 8.x.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# API
python -m app.server
# or
uvicorn app.main:app --port 8080 --reload

# Indexer worker (RabbitMQ -> Elasticsearch)
python -m app.workers.plan_indexer
```

## Tests

The tests use FastAPI's `TestClient` with an in-memory `fakeredis` instance, an overridden
auth dependency, and a mocked RabbitMQ publisher, so no external services are needed.

```bash
pip install -r requirements-dev.txt
pytest
```
