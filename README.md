# Document Intelligence Service

A FastAPI backend that accepts uploaded documents (PDFs, images), runs OCR and structured-data extraction via the Groq API, and persists results to PostgreSQL.

## Project Structure

```
project-root/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── api/routes/          # HTTP route handlers
│   │   ├── core/                # Config, database, logging
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # Business-logic layer (upcoming)
│   │   ├── repositories/        # DB access layer (upcoming)
│   │   └── utils/               # Shared helpers (upcoming)
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── templates/
│   └── static/
├── docs/
├── sample_outputs/
├── .env.example
├── .gitignore
└── README.md
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A running PostgreSQL instance
- A Groq API key (https://console.groq.com)

### 2. Environment setup

```bash
cp .env.example .env
# Edit .env and fill in DATABASE_URL and GROQ_API_KEY
```

### 3. Install dependencies

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Run the development server

```bash
# From the backend/ directory
uvicorn app.main:app --reload
```

The app will:
- Read config from `.env`
- Connect to Postgres and create the `processed_documents` table if it does not exist
- Serve the API at http://localhost:8000

### 5. Verify

```bash
curl http://localhost:8000/api/v1/health
# → {"status": "ok"}
```

Interactive API docs: http://localhost:8000/docs

## Environment Variables

| Variable           | Required | Default       | Description                                   |
|--------------------|----------|---------------|-----------------------------------------------|
| `DATABASE_URL`     | ✅       | —             | PostgreSQL connection string                  |
| `GROQ_API_KEY`     | ✅       | —             | Groq inference API key                        |
| `LOG_LEVEL`        | ❌       | `INFO`        | Logging verbosity                             |
| `MAX_UPLOAD_PAGES` | ❌       | `3`           | Maximum pages per uploaded document           |
| `APP_ENV`          | ❌       | `development` | Deployment environment                        |

## OCR Engine — EasyOCR

The service uses **EasyOCR** for text extraction fallback on scanned/image-based documents.

> **Cold Start Note:** EasyOCR automatically downloads its language model weights (~a few hundred MB) on first run. Internet access is required during this initial execution. The model is cached locally for subsequent runs. This cold-start download applies both locally and during the first startup on server deployment.


## API Endpoints

| Method | Path              | Description          |
|--------|-------------------|----------------------|
| GET    | `/api/v1/health`  | Liveness probe       |

Additional endpoints (process, list, retrieve) are added in subsequent tasks.
