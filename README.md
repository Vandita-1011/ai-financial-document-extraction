# Document Intelligence Service

## 1. Solution Overview
The Document Intelligence Service is a FastAPI backend that accepts uploaded financial documents (PDF, JPEG, PNG), extracts text using a hybrid OCR approach, sends the extracted text to the Groq LLM for structured data extraction, validates the extracted financial figures with deterministic rules, stores the results in PostgreSQL, and exposes the data via a clean JSON API and a simple HTML dashboard.

## 2. Architecture
- **FastAPI**: Serves the HTTP API, static dashboard, and OpenAPI docs.
- **OCR Layer**:
  - Primary: **PyMuPDF** native text extraction for PDF pages.
  - Fallback: **Tesseract OCR** for scanned PDFs and all image files.
- **LLM Extraction**: Calls the **Groq** `/v1/chat/completions` endpoint (model `groq/compound`) to transform raw text into structured JSON.
- **Financial Validation**: Pure‑Python validation logic (`financial_validation_service.py`) checks arithmetic consistency for invoices, balance sheets, profit‑and‑loss statements, and cash‑flow statements.
- **Persistence**: SQLAlchemy with **PostgreSQL** stores each processed document payload in a `processed_documents` table.
- **Frontend**: Minimal Jinja2 templates provide a static dashboard UI.

## 3. Technology Stack and Reasoning
| Layer | Technology | Reason |
|------|------------|--------|
| API | **FastAPI** (v0.115) | High‑performance, async‑ready, automatic OpenAPI generation. |
| Web Server | **uvicorn** (standard) | Production‑grade ASGI server. |
| OCR | **PyMuPDF** (1.28) + **Tesseract OCR** | PyMuPDF efficiently extracts native PDF text; Tesseract handles scanned pages without heavy ML dependencies. |
| LLM | **Groq** SDK (0.9.0) | Low‑latency inference on the free tier, suitable for structured extraction. |
| Validation | Pure Python | Deterministic, no external calls, easy to test. |
| DB | **PostgreSQL** via **SQLAlchemy** (2.0) | Reliable relational store, easy migrations. |
| Frontend | **Jinja2** templates | Simple server‑side rendered dashboard, no SPA overhead. |
| Containerisation | **Docker** multi‑stage build | Small final image, includes Tesseract binary. |

**Engineering History**: The project originally used **EasyOCR** (which depends on PyTorch and TorchVision) for OCR. EasyOCR required large model downloads and substantial CPU/RAM, which exceeded Render's free‑tier resource and disk limits. To make the service compatible with Render Free, we replaced EasyOCR with **Tesseract OCR**, eliminating heavyweight dependencies and cold‑start latency.

## 4. Local Setup Instructions
```bash
# 1. Clone the repository and change to the project root
git clone <repo-url>
cd Project

# 2. Create a Python virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies (root requirements include backend deps)
pip install -r requirements.txt

# 4. Prepare environment variables
cp .env.example .env
# Edit .env and set DATABASE_URL and GROQ_API_KEY accordingly

# 5. Run the development server
cd backend
uvicorn app.main:app --reload
```
The API will be reachable at `http://127.0.0.1:8000`.

## 5. Environment Variables
| Variable | Required? | Default | Description |
|----------|-----------|---------|-------------|
| `DATABASE_URL` | ✅ | – | PostgreSQL connection string (e.g. `postgresql://user:pass@host:5432/db`). |
| `GROQ_API_KEY` | ✅ | – | API key for Groq inference service. |
| `LOG_LEVEL` | ❌ | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `MAX_UPLOAD_PAGES` | ❌ | `3` | Maximum pages allowed per uploaded document. |
| `APP_ENV` | ❌ | `development` | Deployment environment (`development`, `staging`, `production`). |

## 6. Deployed URLs
- **Frontend / Dashboard (root path)**: https://ai-financial-document-extraction-hukn.onrender.com/
- **Backend API base**: https://ai-financial-document-extraction-hukn.onrender.com/api/v1
- **Swagger / OpenAPI docs**: https://ai-financial-document-extraction-hukn.onrender.com/docs
- **GitHub repository**: https://github.com/Vandita-1011/ai-financial-document-extraction

*Note*: The frontend dashboard and the backend API are served from the same Render service; the dashboard is accessed at the root path while the API lives under `/api/v1`.

## 7. API Usage Examples
```bash
# Health check
curl https://ai-financial-document-extraction-hukn.onrender.com/api/v1/health

# List processed documents
curl https://ai-financial-document-extraction-hukn.onrender.com/api/v1/documents

# Retrieve a processed document by name
curl https://ai-financial-document-extraction-hukn.onrender.com/api/v1/documents/<document_name>

# Process a new document (replace <type> and <file>)
curl -X POST \
  -F "file=@<path/to/file>" \
  -F "document_type=<type>" \
  https://ai-financial-document-extraction-hukn.onrender.com/api/v1/documents/process
```
Supported `document_type` values are `invoice`, `balance_sheet`, `profit_and_loss`, and `cash_flow`.

## 8. OCR and LLM Services
- **Native PDF extraction** uses `PyMuPDF` (`page.get_text()`). If the extracted text is shorter than **10 characters**, the page is considered a scanned image.
- **Tesseract OCR** rasterises the PDF page at 150 DPI and runs `pytesseract.image_to_string`. The OCR flag (`ocr_used`) is reported per page and in the overall response.
- **LLM extraction** sends the concatenated page texts to Groq's `groq/compound` model, which returns a structured JSON payload that is later validated.

## 9. Confidence Scoring
The service **does not implement confidence scoring** for the extracted fields. All validation results are binary (`PASS`/`FAIL`) based on deterministic arithmetic rules.

## 10. Financial Validation Rules
The `financial_validation_service` runs a suite of checks for each document type:
- **Invoice**: line‑item quantity × unit‑price ≈ amount, subtotal vs reported subtotal, tax inclusion, total vs subtotal + tax − discount, cash‑paid vs change.
- **Balance Sheet**: total assets ≈ total liabilities + equity, asset‑item sum ≈ total assets, liability‑item sum ≈ total liabilities + equity.
- **Profit & Loss**: total income = interest + other income, total expenditure = interest + operating + provisions, net profit calculations, appropriation of current and carried‑forward profit.
- **Cash Flow**: cash‑flow reconciliation (operating + investing + financing + FX ≈ net change) and opening/closing cash reconciliation.

**Tolerance Logic**: For each numeric comparison the code calls `_tolerance(reported)` defined as `max(0.01, 0.01 * abs(reported))`. This means the allowed variance is the larger of a fixed $0.01 absolute value or 1 % of the reported amount.

Each check returns a calculated value, the reported value, variance, and a `PASS`/`FAIL` status. An overall status aggregates the individual results.

## 11. Database and Persistence
A single table `processed_documents` (created by SQLAlchemy on startup) stores:
- `id` (PK)
- `document_name`
- `document_type`
- `processing_status`
- `result_json` (the full API response JSON)
- `created_at`
The repository layer (`document_repository.py`) provides `save_document`, `get_by_name`, and `get_all` helpers used by the API routes.

## 12. Known Limitations
- **Render free tier** limits CPU and memory; large PDFs may exceed the page limit (`MAX_UPLOAD_PAGES`).
- Only the four document types listed above are supported.
- No confidence scores are returned for extracted fields.
- OCR quality depends on the quality of the scanned image; very low‑resolution scans may produce empty text.
- The Groq free tier enforces request size limits; extremely large documents may need to be split.
- **UI Limitation**: The browser‑based upload workflow through the dashboard UI has not yet been manually click‑tested end‑to‑end, although the underlying API it depends on has been fully verified through direct API calls covering all four document types.

## 13. Production Improvement Notes
- **Caching** of Groq responses for identical documents could reduce cost and latency.
- **Async OCR**: Off‑load Tesseract calls to a background worker (e.g., Celery) to avoid blocking the request thread.
- **Horizontal scaling**: Deploy multiple FastAPI workers behind a load balancer for higher throughput.
- **Monitoring**: Integrate Prometheus metrics and Grafana dashboards for request latency and error rates.
- **Security**: Harden CORS policy for production and rotate API keys regularly.


