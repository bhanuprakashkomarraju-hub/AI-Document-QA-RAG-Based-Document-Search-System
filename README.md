# Healthcare Document Intelligence System (RAG)

A production-oriented healthcare RAG application for querying patient records, clinical notes, and compliance PDFs with grounded answers and source evidence.

## Why This Exists

Healthcare teams often spend too much time searching through fragmented PDFs.  
This system converts those documents into a semantic knowledge layer so users can ask natural-language questions and get traceable answers quickly.

## What It Does

- Ingests healthcare PDFs (`POST /upload`)
- Extracts and chunks document text (configurable size + overlap)
- Builds embeddings and stores vectors in FAISS
- Uses hybrid retrieval (keyword shortlist + vector search + reranking)
- Generates context-grounded answers
- Returns retrieved source chunks with every response
- Tracks runtime metrics and cache performance


## Screenshots
![WhatsApp Image 2026-03-27 at 3 44 21 PM](https://github.com/user-attachments/assets/645e58e8-e6a3-4204-a066-37822304ab2b)

![Swagger Overview](test/results/screenshots/swagger_overview.png)
![Swagger Query CO2 Result](test/results/screenshots/swagger_query_co2_result.png)
![Swagger Query Romulus Result](test/results/screenshots/swagger_query_romulus_result.png)

## Core Capabilities

- **Backend:** FastAPI, modular service architecture
- **Retriever controls:** `TOP_K`, `SIMILARITY_THRESHOLD`, query-time overrides
- **Caching:** in-memory TTL cache for repeated queries
- **Observability:** query logs + response latency + retrieved sources
- **Metrics endpoint:** `GET /metrics`
- **Frontend:** React + Tailwind chat UI with source panel
- **Evaluation:** compare with-retrieval vs without-retrieval performance

## Project Structure

```text
app/
  api/
  core/
  db/
  services/
  utils/
  evaluation/
frontend/
test/
requirements.txt
render.yaml
```

## Quick Start

### 1) Backend setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` in project root:

```env
PROJECT_NAME=Healthcare Document Intelligence System
PROJECT_VERSION=2.0.0
PROJECT_DESCRIPTION=RAG platform for patient records, clinical notes, and compliance documents.

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_MODEL=all-MiniLM-L6-v2

DATA_DIR=data
TOP_K=5
SIMILARITY_THRESHOLD=0.7
CHUNK_SIZE=500
CHUNK_OVERLAP=100
QUERY_CACHE_TTL_SECONDS=300

CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Run backend:

```bash
uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

### 2) Frontend setup

```bash
cd frontend
npm install
npm run dev
```

- Frontend: `http://localhost:5173`
- Optional frontend env (`frontend/.env`):

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## API Overview

### `POST /upload`
Upload and ingest a healthcare PDF.

Example success:

```json
{
  "status": "success",
  "filename": "patient_record.pdf",
  "chunks_created": 14,
  "characters_processed": 5340
}
```

### `POST /query`
Ask a healthcare question and get answer + source chunks.

Request:

```json
{
  "question": "What medications is the patient taking?"
}
```

Optional query params:
- `top_k`
- `threshold`
- `use_retrieval`
- `bypass_cache`

Response:

```json
{
  "answer": "...",
  "retrieved_chunks": [
    {
      "text": "...",
      "source": "patient_record.pdf",
      "chunk_id": 3,
      "score": 0.61,
      "similarity": 0.80,
      "keyword_score": 0.33,
      "rerank_score": 0.70
    }
  ],
  "response_time_ms": 29.1
}
```

### `GET /metrics`

```json
{
  "total_queries": 120,
  "avg_response_time": 28.6,
  "cache_hits": 45,
  "cache_misses": 75
}
```

## Example Healthcare Questions

- What medications is the patient currently taking?
- Summarize discharge notes for this patient.
- What allergies are documented in the record?
- What follow-up instructions were provided?

## Evaluation

Run:

```bash
python -m app.evaluation.run_evaluation --base-url http://127.0.0.1:8000 --top-k 5 --threshold 0.7
```

Outputs:
- average latency
- qualitative accuracy score
- JSON report: `test/results/healthcare_eval_metrics.json`


