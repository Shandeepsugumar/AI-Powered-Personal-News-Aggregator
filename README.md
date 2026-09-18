# FeedToRead — Plan A Backend

Two-stage LLM pipeline that ingests raw content from n8n, deduplicates, merges related stories, detects conflicting facts, and serves a ranked newspaper-style JSON feed.

```
n8n → POST /ingest → LLM 1 (Groq) → Embedding → Candidate Retrieval → LLM 2 (OpenRouter) → SQLite → GET /newspaper
```

---

## Setup

```bash
# 1. Clone and checkout the feature branch
git clone https://github.com/Yukeshvenkadesh/FeedRead.git
cd FeedRead
git checkout feature/plan-a-backend

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
# Then edit .env and fill in your real API keys

# 5. Start the server
uvicorn main:app --reload --port 8000
```

The server creates `feedtoread.db` (SQLite) automatically on first run. The sentence-transformers model (`all-MiniLM-L6-v2`) downloads automatically on first run (~80MB).

---

## API Reference

### `POST /ingest` — Submit a single content item

**Call this once per fetched item** (per video/article/tweet). Do NOT batch multiple items in one call. The service handles deduplication and merging internally.

#### Request Body

```json
{
  "source_type": "blog",
  "source_name": "TechCrunch",
  "source_url": "https://techcrunch.com/2026/09/18/iphone-18",
  "title": "iPhone 18 Announced",
  "content": "Apple has officially announced the iPhone 18 today in Cupertino...",
  "published_at": "2026-09-18T10:00:00Z",
  "fetched_at": "2026-09-18T10:05:00Z"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `source_type` | string | ✅ | `"blog"`, `"youtube"`, `"newsletter"`, `"twitter"` |
| `source_name` | string | ✅ | Human-readable source name (e.g. `"TechCrunch"`) |
| `source_url` | string | ✅ | Original URL of the content |
| `title` | string | optional | Title/headline if available |
| `content` | string | ✅ | **Plain extracted text** — not HTML. YouTube transcripts, blog text, etc. already extracted by n8n upstream |
| `published_at` | string | optional | ISO 8601 timestamp |
| `fetched_at` | string | optional | ISO 8601 timestamp (defaults to now) |

#### Response

```json
{
  "status": "success",
  "story_group_id": 1,
  "decision": "merge"
}
```

| `decision` value | Meaning |
|------------------|---------|
| `"new_group"` | First item on this topic — created a new story group |
| `"merge"` | Merged into an existing story group (same event) |
| `"separate"` | Related topic found but different event — kept separate |

Other possible responses:
- `{"status": "skipped", "reason": "Exact duplicate content hash"}` — identical content already ingested
- `{"status": "skipped", "reason": "Not news"}` — LLM 1 classified as spam/filler
- `{"status": "skipped", "reason": "Content not meaningful/too short"}` — content under 20 chars
- `{"status": "failed", "reason": "LLM 1 API error"}` — API call failed, item saved with `processing_status="failed"`

---

### `GET /newspaper?user_id=<id>` — Get the newspaper edition

Returns all active stories from the last 48 hours, ranked by importance.

#### Response

```json
{
  "_id": "edition_user123",
  "editionNumber": 3,
  "dateString": "2026-09-18",
  "createdAt": "2026-09-18T15:30:00Z",
  "stories": [
    {
      "id": "1",
      "headline": "Apple Unveils iPhone 18 with Titanium Frame",
      "category": "TECHNOLOGY",
      "stance": "NEUTRAL STANCE",
      "importance": "lead",
      "summary": "Apple announced the iPhone 18 at a live event...",
      "sources": [
        {
          "name": "TechCrunch",
          "url": "https://techcrunch.com/...",
          "type": "BLOG"
        }
      ],
      "timestamp": "2026-09-18T15:30:00Z"
    }
  ]
}
```

**`importance` values**: `"lead"` → `"major"` → `"minor"` (based on source count and recency)

**`editionNumber`**: Increments every time `/newspaper` is called for this `user_id`. Content only changes when new stories are ingested — calling `/newspaper` multiple times without new ingests returns the same stories with an incremented edition number.

---

### `POST /mark_read` — Mark a story as read

```json
{ "user_id": "user123", "story_id": 1 }
```

### `POST /retry-failed` — Retry items that failed LLM processing

Retries all items with `processing_status="failed"` through the full pipeline.

### `GET /health` — Health check

Returns `{"status": "ok"}`.

---

## Architecture

| Stage | Component | Model / Tool |
|-------|-----------|-------------|
| **LLM 1** — Summarize | Groq API | `openai/gpt-oss-120b` (configurable in `ai_service.py`) |
| **Embedding** | Local | `all-MiniLM-L6-v2` (sentence-transformers) |
| **Candidate Retrieval** | Cosine similarity | Top-5 from active story groups |
| **LLM 2** — Merge/Separate | OpenRouter API | `deepseek/deepseek-v4-flash-0731:free` |
| **Storage** | SQLite | WAL mode, auto-created |

### Pipeline Flow

1. **Content Parser** — Light cleanup, content hash for exact dedup
2. **LLM 1** — Summarize, extract headline/category/event/key_facts, classify `is_news`
3. **Embedding** — Encode headline+summary with sentence-transformers
4. **Candidate Retrieval** — Find top-5 similar active story groups (cosine similarity, 48h window)
5. **LLM 2** — Decide merge/separate/new_group; if conflicting facts, explicitly attributes both claims in the merged summary
6. **Importance Ranking** — Recompute `lead`/`major`/`minor` based on source count

---

## Known Limitations

- **Free-tier API rate limits**: Both Groq and OpenRouter free tiers have rate limits (~20 req/min for OpenRouter, variable for Groq). Occasional delays or timeouts are expected during high-volume ingestion.
- **Failed items are recoverable**: When an LLM API call fails, the item is saved with `processing_status="failed"` (not silently dropped). Call `POST /retry-failed` to reprocess them.
- **Freshness window**: Stories older than 48 hours are excluded from candidate retrieval and the `/newspaper` response.
- **Single-worker**: Default uvicorn runs a single worker. For production, consider `--workers 2` but note SQLite write concurrency limits.

---

## Running Tests

```bash
# Start the server in one terminal
uvicorn main:app --port 8000

# Run the test suite in another terminal
python tests.py
```

The test suite covers: exact dedup, paraphrase merge (3 runs), same-topic-different-event separation (3 runs), conflicting fact merge (3 runs), cross-batch merge, edition counter, and importance ranking.

---

## Project Structure

```
├── main.py              # FastAPI endpoints (/ingest, /newspaper, /mark_read, /retry-failed)
├── ai_service.py        # LLM 1 (Groq) + LLM 2 (OpenRouter) API calls, embedding
├── database.py          # SQLAlchemy models + SQLite config (WAL mode)
├── content_parser.py    # Content cleanup, hashing, meaningful-content check
├── ranking.py           # Importance ranking logic (lead/major/minor)
├── tests.py             # 7-test verification suite
├── requirements.txt     # Python dependencies
├── .env.example         # Template for required API keys
└── .gitignore           # Excludes .env, .venv, __pycache__, *.db
```
