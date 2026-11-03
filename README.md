# AI Assessment Platform

An LLM-powered assessment platform with two modes: **hiring** (recruiters generate, review and publish tests, invite candidates by single-use link, and review AI-graded, browser-proctored attempts) and **practice** (learners paste notes and get a quiz with instant feedback).
FastAPI + SQLAlchemy backend, React + TypeScript frontend, pluggable Anthropic/OpenAI providers, and a deterministic fake model so the whole thing runs without an API key.

| Assessment builder | Candidate test | Results and integrity |
| --- | --- | --- |
| ![Builder: generate, review and edit questions](docs/screenshots/1-builder.png) | ![Candidate taking a timed, proctored test](docs/screenshots/2-candidate-test.png) | ![Recruiter results with integrity summary](docs/screenshots/3-results.png) |

## Why it's interesting

- **LLM output is never trusted.** Every generation and grading reply is parsed into Pydantic models, checked against domain rules (an MCQ's answer index exists, a grade has exactly the rubric's criteria and never exceeds their points) and gets one repair attempt before failing with a clear error.
- **Grades are auditable.** Each AI score stores the model name and prompt version; a recruiter override is stored next to the AI score instead of replacing it.
- **Proctoring that respects candidates.** Consent screen first; browser-only signals (tab switches, focus, full screen, copy/paste, periodic webcam stills); a transparent rule-based summary. No face recognition or biometric analysis, by design.
- **Safe Exam Browser support.** Optional per assessment: the API verifies SEB's `X-SafeExamBrowser-RequestHash` header, unit-tested against a pinned vector.
- **One provider-agnostic LLM layer.** A tiny `LLMClient` protocol with Anthropic, OpenAI and `FakeLLM` implementations sharing one policy: per-call timeout, exponential backoff with full jitter on 429/5xx, and a client-side concurrency limiter.

## Architecture

```mermaid
flowchart LR
    subgraph Browser["React + TypeScript (Vite)"]
        R["Recruiter<br/>builder · invites · results"]
        C["Candidate<br/>consent · timed test · proctoring hook"]
        P["Learner<br/>practice quiz"]
    end
    subgraph API["FastAPI"]
        RT["Routers<br/>JWT or invite token · slowapi limits"]
        SEB["seb.py<br/>request-hash check"]
        GEN["generation.py<br/>prompt → JSON → dedupe"]
        GR["grading.py<br/>MCQ exact · rubric via LLM"]
        JOB["jobs.py<br/>background grading"]
        INT["integrity.py<br/>rule-based summary"]
    end
    LLM["LLMClient<br/>Anthropic · OpenAI · FakeLLM<br/>timeout · retry + jitter · limiter"]
    DB[("SQLite / Postgres")]
    FS[("webcam stills on disk")]

    R & C & P --> RT
    RT --> SEB
    RT --> GEN --> LLM
    RT -- submit --> JOB --> GR --> LLM
    RT --> INT
    RT --> DB
    JOB --> DB
    RT --> FS
```

Request flow for a candidate: `GET /api/take/{token}` (info) → consent → `POST /start` (server stores the deadline) → `POST /events` and `POST /snapshots` while the test runs → `POST /submit` (atomically closes the invite, returns 202) → background job grades every answer → the recruiter sees `GET /api/invites/{id}/result`.

```
backend/app/
  main.py            app factory, error handlers, SPA serving, log redaction
  questions.py       Pydantic question models (MCQ, short answer, coding)
  llm/               LLMClient protocol, retry/limiter, structured output, providers, FakeLLM
  services/          generation, dedup, grading, integrity: pure logic, no HTTP or DB
  routers/           auth, assessments, candidate, results, practice
  models.py, db.py   SQLAlchemy 2 tables
  seb.py, security.py, ratelimit.py, jobs.py, seed.py
frontend/src/
  pages/             Login, Dashboard, Builder, Results, TakeTest, Practice
  components/        QuestionCard (view + edit), GenerationForm, AnswerInput, Status
  lib/               useProctoring, useLoad, format helpers (+ vitest)
```

## Quickstart

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22+.

```bash
make install   # uv sync (backend/.venv) + npm ci (frontend)
make demo      # builds the UI, seeds demo data with FakeLLM, serves everything on :8000
```

Then open <http://localhost:8000>:

1. Sign in as `demo@example.com` / `demo-password`. A published sample assessment is already there.
2. Create an assessment, generate questions, edit one, publish, and create an invite link.
3. Open the link in a private window to take the test as the candidate (the seed also prints a ready-made link).
4. Back as the recruiter, open **View results**: scores, rubric justifications, override, and the integrity summary.
5. Try **Practice** (no login): paste study notes and check answers one by one.

Demo mode needs no API key. To use a real model, copy `.env.example` to `backend/.env`, set `LLM_PROVIDER=anthropic` (or `openai`) and the key, then run `make run` (API with reload on :8000) and `cd frontend && npm run dev` (UI on :5173, proxying `/api`).

## Configuration

All settings are environment variables (or `backend/.env`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `fake` | `fake`, `anthropic` or `openai` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | – / `claude-sonnet-5-5` | Anthropic credentials and model |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | – / `gpt-6.1-sol` | OpenAI credentials and model |
| `LLM_TIMEOUT_SECONDS` | `60` | Per-call timeout |
| `LLM_MAX_RETRIES` | `3` | Retries on 429/5xx/network errors (jittered backoff) |
| `LLM_MAX_CONCURRENCY` | `4` | Client-side cap on in-flight LLM calls |
| `DATABASE_URL` | `sqlite:///./data/app.db` | For Postgres: `uv sync --extra postgres`, then `postgresql+psycopg://user:pass@host/db` |
| `JWT_SECRET` | random per process | At least 32 characters; set it in production |
| `JWT_TTL_MINUTES` | `120` | Recruiter session length |
| `INVITE_TTL_HOURS` | `72` | Default invite expiry |
| `DEDUP_THRESHOLD` | `0.85` | Similarity above which a generated question is a near-duplicate |
| `SUBMIT_GRACE_SECONDS` | `60` | Late-submit tolerance after the deadline |
| `SNAPSHOT_DIR` / `SNAPSHOT_MAX_BYTES` | `./data/snapshots` / `500000` | Webcam still storage and size cap |
| `PUBLIC_BASE_URL` | empty | Public origin, needed for SEB checks behind a proxy |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated dev origins |
| `RATE_LIMIT_ENABLED` | `true` | Turn slowapi limits off (tests only) |

## How to test

```bash
make lint   # ruff check + ruff format --check, tsc --noEmit + prettier --check
make test   # pytest with a 95% coverage gate, vitest
```

The backend suite (99 tests, ~99% coverage) never touches the network: the provider adapters run through the real Anthropic and OpenAI SDKs over a mocked HTTP transport (429 → retry, 400 → no retry, refusals, truncation), and everything else uses `FakeLLM` or a scripted fake that returns malformed JSON to exercise the repair path. CI runs both suites plus the production build (`.github/workflows/ci.yml`).

## Proctoring and privacy

Before the timer starts, the candidate sees exactly what is collected and must tick a consent box.

| Signal | How it is captured |
| --- | --- |
| Tab switches and time away | `visibilitychange` (hidden/visible pairs give total time away) |
| Window focus lost | `blur` |
| Leaving full screen | `fullscreenchange` (the test requests full screen on start) |
| Copy and paste | `copy` / `paste` events (paste length only, never the content) |
| Webcam stills | `getUserMedia`, a 320×240 JPEG every N seconds, uploaded to the API |

The backend turns these into an **integrity summary**: counts, a timeline, flags (e.g. left the tab 3+ times, away 60s+, any paste, missing webcam stills) and a low/medium/high level from the number of warnings. It is labelled as signals for a human, not a verdict.

**No face recognition, face matching, gaze tracking or any other biometric analysis is done, on purpose.** Those techniques have uneven accuracy across skin tones, lighting and disabilities, and they process biometric data that many jurisdictions regulate strictly. Here the images are only shown to the recruiter, next to the timeline.

## Safe Exam Browser

[Safe Exam Browser](https://safeexambrowser.org) (SEB) is a lockdown browser. When an assessment has **Require Safe Exam Browser** on, every candidate API request must carry `X-SafeExamBrowser-RequestHash`, which SEB computes as `SHA-256(absolute request URL without #fragment + Browser Exam Key)` in lowercase hex. The API recomputes it with the key saved on the assessment and compares in constant time (`backend/app/seb.py`). Anything else gets a 403 that the candidate page explains.

Creating the config with SEB's own tool:

1. Install SEB for Windows or macOS. On Windows, open the **SEB Configuration Tool**; on macOS, open SEB's **Preferences** window, which is its config editor.
2. **General**: set *Start URL* to the candidate's invite link (`https://your-host/take/<token>`). Links are per candidate, so this means one config file per candidate.
3. **Exam** (macOS: *Exam* pane): enable *Use Browser Exam Key and Configuration Key* (sends the keys in HTTP headers) and copy the **Browser Exam Key** shown there.
4. Save the configuration as a `.seb` file. The Browser Exam Key changes whenever settings change and also depends on the SEB version, so copy it after the final save and have candidates use the same SEB version.
5. In the builder, tick **Require Safe Exam Browser** and paste the key. If the app runs behind a reverse proxy, set `PUBLIC_BASE_URL` so the server hashes the same URL SEB requested.
6. Send the `.seb` file to the candidate; opening it starts SEB at the invite link.

## Design decisions and tradeoffs

- **Text in, JSON out, Pydantic validation, one repair.** Rather than each provider's native structured-output mode, every provider (and the fake) goes through the same `complete_json` path. Cost: an occasional extra call when the first reply is invalid. Benefit: identical behaviour and tests across providers.
- **SDK retries off, one explicit policy.** Both SDKs run with `max_retries=0`; `call_with_retries` retries 429/5xx/connection errors with full-jitter backoff, and a `RateLimiter` caps concurrency and spaces call starts. Anthropic requests also opt into server-side refusal fallbacks.
- **One generation call per question type.** This guarantees the requested mix and keeps each schema simple. Near-duplicates are removed afterwards by normalising text and comparing with `difflib` (ratio ≥ 0.85), against each other and existing questions. It is lexical, not semantic; embeddings would catch paraphrases at the cost of another model call.
- **Grading resists prompt injection.** The candidate answer is fenced in `<answer>` tags and the system prompt says to treat it as data. The rubric check also means a manipulated grade cannot rename criteria or exceed their points.
- **Single-use invites.** Only a SHA-256 of the token is stored (the link is shown once, like an API key). Submission claims the attempt with an atomic `UPDATE … WHERE status = 'in_progress'`, so two racing submits cannot both store answers. Tokens are redacted from access and rate-limit logs.
- **The server owns the clock.** The deadline is stored at start; the client counts down from the server's `remaining_seconds`, auto-submits at zero (with retries), and a 60-second grace absorbs network delay. Reloading resumes the same attempt, and draft answers survive in `sessionStorage`.
- **Background grading without long transactions.** `BackgroundTasks` grades after the 202 response. The job reads, closes its session, calls the LLM, then writes in one short transaction, so slow calls never hold a SQLite write lock. A failed answer is logged, marked for manual scoring, and the attempt shows *Needs review*.
- **Every route has an explicit rate limit.** slowapi keys by client IP plus path (so each invite link gets its own budget), returns 429 with `Retry-After`, and a test fails if any router endpoint lacks a `@limiter.limit`.
- **Pure core, thin shell.** `services/` and `seb.py` are plain functions over Pydantic models and datetimes, so most logic is tested without HTTP or a database.

## Limitations and roadmap

- Grading jobs live in process: a restart between submit and grading leaves an attempt in *Grading*. A durable queue (or re-grade on startup) is next.
- Coding answers are graded by the LLM against a reference solution; no sandboxed test execution yet.
- Schema is created with `create_all`; add Alembic migrations and run CI against Postgres.
- Rate-limit counters are in memory (one process). Use Redis storage for multiple workers.
- The recruiter JWT is kept in `localStorage`; an httpOnly cookie would reduce XSS exposure.
- SEB: verify the Config Key header as well, and add a token-entry start page so one config can serve every candidate.
- Webcam stills need a retention and deletion policy and encryption at rest before real use.

## License

MIT, see [LICENSE](LICENSE).
