# Technical explanation

## Architecture

`app.main` wires the HTTP API to SQLAlchemy models and service modules. `pdf_extractor` owns PDF validation/text/OCR; `parser` converts extracted text into nullable typed fields; `reconciliation` matches vendor and PO, detects duplicates, checks arithmetic and chooses a decision. The API persists the source file, extraction, checks, decision, and human review in SQLite. The React page calls the API and renders its returned records.

## Processing services

- `extract_pdf(path)`: input is a saved PDF path; output is text, extraction method, and warnings. It uses PyMuPDF text extraction, falling back to Tesseract OCR only when available and text is sparse.
- `parse_invoice(text)`: input is extracted text; output is normalized invoice fields and confidence estimates based on explicit label/amount/date matches. Unfound data remains null.
- `reconcile(session, invoice)`: input is the current database session and parsed values; output is status, checks, and reasons. It prefers vendor IDs, uses cautious name matching, honors exact PO references, and flags ambiguous candidates. Partial invoices consume only their amount after approval.
- `record_review`: saves a separate human action without erasing the automated result.

SQLite tables cover vendors, POs, invoices, settings, and reviews. Database writes are transactional; SQLite serializes writes. A production multi-user deployment should add authorization, queueing, and stronger concurrent reservation semantics.

## Important design choices

No external AI service or currency conversion is used. Automatic approval requires all critical checks to pass. Unknown vendors, ambiguous matches, low-confidence/missing data, currencies that do not agree, suspicious duplicates, and PO overages route to review. Confirmed duplicate files or invoice identifiers are rejected. The API docs expose request/response schemas at `/docs`.
