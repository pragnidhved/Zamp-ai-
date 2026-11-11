# Zamp Invoice Reconciliation Demo

A local, explainable invoice and purchase order reconciliation application. The backend is a modular FastAPI service backed by SQLite. It extracts text from PDFs (PyMuPDF), optionally runs Tesseract OCR when installed, parses common invoice fields, checks vendor/PO/duplicate/financial rules, and stores decisions and audit data. The React/Vite client uploads one or more PDFs and displays actual processing results.

An alternative Streamlit Community Cloud UI is available from the project-root `streamlit_app.py`. See [STREAMLIT_CLOUD.md](STREAMLIT_CLOUD.md) for its deployment steps and data-handling limits. The cloud demo uses per-browser-session in-memory data; the local FastAPI/React version remains the persistent local app.

## Requirements

- Windows 11, Python 3.11+, Node.js 20+
- Tesseract OCR is optional for text PDFs and required for scanned PDFs. Install the Windows build and set `TESSERACT_CMD` if it is not on PATH.

## Run

In PowerShell, from this folder:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed_data.py
python generate_samples.py
uvicorn app.main:app --reload --port 8000
```

In another PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Swagger API docs are at http://localhost:8000/docs. SQLite and uploads are stored under `backend/data` and `backend/uploads`.

## Workflow and rules

Uploads are validated for extension, PDF signature, and 15 MB size, then hashed. The extractor tries embedded text first; a short text result triggers OCR if Tesseract is available. Regex parsing returns nullable values and field confidence signals. Name matching uses normalized exact matches or a conservative similarity threshold. A stated PO number is authoritative; missing PO references are matched only when exactly one vendor/currency/amount candidate exists. Duplicate file hash or vendor plus invoice number is a hard duplicate. Financial checks compare subtotal plus tax to total using configurable rounding tolerance, check currency, vendor approval, PO state and remaining balance. Partial billing is allowed. Any uncertain or failing check prevents automatic approval. Decisions are deterministic and include reasons/checks. Human review is recorded separately from the automated decision.

The seeded demo provides five vendors and ten purchase orders. `generate_samples.py` creates 15 different demonstration invoices plus a byte-identical duplicate in `sample_data/invoices`; upload these files to demonstrate extraction and review cases. Invoice 2 is image-only and needs Tesseract. The app accepts real user PDFs and PO CSV imports (`po_number,vendor_id,currency,total_amount,previously_invoiced,status`).

## API

- `POST /api/invoices/upload` (multipart files; processes immediately)
- `GET /api/invoices`, `GET /api/invoices/{id}`, `GET /api/invoices/{id}/progress`, `GET /api/invoices/{id}/file`
- `POST /api/invoices/batch-process` (uploaded invoice IDs)
- `POST /api/invoices/{id}/review` (reviewer, action, reason, notes)
- `GET /api/dashboard/summary`, `GET /api/dashboard/trends`
- `GET /api/vendors`, `POST /api/vendors`, `PUT /api/vendors/{id}`
- `GET /api/purchase-orders`, `POST /api/purchase-orders`, `POST /api/purchase-orders/import`
- `GET /api/settings`, `PUT /api/settings`

## Limitations

Invoice layouts vary. This baseline parser recognizes common labels but is not a general document understanding model; inspect low-confidence fields and use human review. OCR quality depends on local Tesseract and image quality. Line-item reconciliation and international currency conversion are intentionally conservative: unverified comparisons are sent to review. There is no authentication; bind to localhost for this interview demo. Processing runs synchronously per request.

## Troubleshooting

- If activation is blocked: `Set-ExecutionPolicy -Scope Process Bypass`.
- If OCR reports unavailable: install Tesseract, then set `$env:TESSERACT_CMD='C:\Program Files\Tesseract-OCR\tesseract.exe'` before starting the API.
- If port 8000 is occupied, choose another Uvicorn port and update `frontend/src/api.ts`.
- CSV headers are case-insensitive; required headers are listed above. Invalid rows are rejected with a useful API error.

## Backend test suite

From `backend` with the virtual environment active, run `pytest -q`. The current project environment used to prepare this folder did not have a working Python runtime, so these tests are included but were not executed here.
