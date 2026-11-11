from __future__ import annotations

import csv
import hashlib
import io
import sys
import tempfile
from pathlib import Path

import pymupdf
import streamlit as st
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.db import Base  # noqa: E402
from app.models import Invoice, PurchaseOrder, Review, Setting, Vendor  # noqa: E402
from app.services.parser import parse_invoice  # noqa: E402
from app.services.pdf_extractor import extract_pdf  # noqa: E402
from app.services.reconciliation import reconcile  # noqa: E402

MAX_UPLOAD = 15 * 1024 * 1024
SAMPLE_DIR = ROOT / "sample_data" / "invoices"

st.set_page_config(page_title="Invoice Reconciliation", page_icon="🧾", layout="wide")

st.markdown("""
<style>
    :root { --ink: #17243a; --muted: #63728a; --line: #e4eaf2; --accent: #3765d8; }
    [data-testid="stAppViewContainer"] { background: #f5f7fb; }
    [data-testid="stHeader"] { background: rgba(245,247,251,.92); }
    [data-testid="stSidebar"] { background: #111d33; }
    [data-testid="stSidebar"] * { color: #e8eefb; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #aab8d0; }
    [data-testid="stSidebar"] [role="radiogroup"] { gap: .35rem; }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        padding: .55rem .7rem; border-radius: .65rem; transition: background .15s ease;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover { background: #1d2d4a; }
    [data-testid="stSidebar"] [role="radiogroup"] label p { color: #e8eefb !important; font-weight: 550; }
    [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
    .hero { padding: 1.45rem 1.7rem; border: 1px solid #e4eaf2; border-radius: 1rem;
        background: linear-gradient(115deg, #fff 5%, #edf3ff 100%); margin: .25rem 0 1rem; }
    .hero-kicker { color: #3765d8; font-size: .75rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
    .hero-title { color: #17243a; font-size: 1.85rem; font-weight: 750; margin: .25rem 0; }
    .hero-copy { color: #63728a; margin: 0; }
    [data-testid="stMetric"] { background: white; border: 1px solid #e4eaf2; border-radius: .85rem; padding: .9rem 1rem; }
    [data-testid="stMetricLabel"] p { color: #63728a; }
    div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: .85rem; }
    h2, h3 { color: #17243a; }
</style>
""", unsafe_allow_html=True)


def get_session():
    """Create one isolated in-memory SQLite database per browser session."""
    if "invoice_session" not in st.session_state:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        db = factory()
        seed_demo_data(db)
        st.session_state["invoice_engine"] = engine
        st.session_state["invoice_session"] = db
    return st.session_state["invoice_session"]


def seed_demo_data(db):
    if db.scalar(select(func.count()).select_from(Vendor)):
        return
    vendors = [
        ("V001", "ABC Technologies", True, "INR"),
        ("V002", "XYZ Solutions", True, "INR"),
        ("V003", "Global Supplies", True, "INR"),
        ("V004", "Unknown Traders", False, "INR"),
        ("V005", "Northwind Services", True, "USD"),
    ]
    for vendor_id, name, approved, currency in vendors:
        db.add(Vendor(id=vendor_id, name=name, approved=approved, currency=currency))
    for number in range(1, 11):
        vendor = vendors[(number - 1) % len(vendors)]
        db.add(PurchaseOrder(
            number=f"PO-{1000 + number}", vendor_id=vendor[0], currency=vendor[3],
            total_amount=float(25000 + number * 5000),
            previously_invoiced=5000.0 if number % 3 == 0 else 0.0, status="OPEN",
        ))
    for key, value in (("amount_tolerance_percent", 2.0), ("amount_tolerance_absolute", 1000.0), ("rounding_tolerance", 1.0)):
        db.add(Setting(key=key, value=value))
    db.commit()


def setting(db, key, default):
    saved = db.get(Setting, key)
    return float(saved.value) if saved else float(default)


def process_pdf(db, filename: str, content: bytes):
    if len(content) > MAX_UPLOAD:
        raise ValueError("This PDF is larger than 15 MB.")
    if not content.startswith(b"%PDF-"):
        raise ValueError("The selected file is not a valid PDF.")
    digest = hashlib.sha256(content).hexdigest()
    safe_name = Path(filename).name
    # The document exists only in a short-lived temp folder while it is parsed.
    with tempfile.TemporaryDirectory(prefix="invoice-demo-") as temp_dir:
        path = Path(temp_dir) / f"{digest}.pdf"
        path.write_bytes(content)
        inv = Invoice(filename=safe_name, path=str(path), file_hash=digest)
        db.add(inv)
        db.commit()
        db.refresh(inv)
        # Keep the source PDF in this browser session so it can be downloaded from
        # both the processing screen and the history screen. It is never persisted.
        st.session_state.setdefault("processed_pdf_content", {})[inv.id] = content
        try:
            text, method, warnings = extract_pdf(str(path))
            data = parse_invoice(text)
            result = reconcile(db, data, digest, inv.id)
            result["warnings"].extend(warnings)
            inv.method = method
            inv.extracted_text = text[:50000]
            inv.data = data
            inv.decision = result["decision"]
            inv.result = result
            if inv.decision == "APPROVED" and result.get("po_number"):
                po = db.get(PurchaseOrder, result["po_number"])
                if po:
                    po.previously_invoiced += data["total_amount"]
            db.commit()
            return inv
        except Exception:
            db.rollback()
            inv = db.get(Invoice, inv.id)
            inv.decision = "NEEDS_REVIEW"
            inv.result = {
                "decision": "NEEDS_REVIEW", "checks": [],
                "reasons": ["PDF processing failed. Check that the file is readable and retry."],
                "warnings": [], "recommended_action": "Check the PDF and retry.",
            }
            db.commit()
            return inv


def record_review(db, invoice, reviewer, action, reason, notes):
    review = Review(invoice_id=invoice.id, reviewer=reviewer, action=action, reason=reason, notes=notes)
    db.add(review)
    invoice.human_decision = action
    invoice.review_notes = reason + (f" — {notes}" if notes else "")
    db.commit()


def invoice_summary(inv):
    data = inv.data or {}
    return {
        "File": inv.filename,
        "Invoice number": data.get("invoice_number") or "—",
        "Vendor": data.get("vendor_name") or "—",
        "Total": f"{data.get('currency') or ''} {data.get('total_amount') if data.get('total_amount') is not None else '—'}",
        "Extraction": inv.method,
        "Automated decision": inv.decision,
        "Human decision": inv.human_decision or "—",
    }


db = get_session()

all_invoices = db.scalars(select(Invoice).order_by(Invoice.id.desc())).all()
total = len(all_invoices)
approved = sum(inv.decision == "APPROVED" for inv in all_invoices)
review = sum(inv.decision == "NEEDS_REVIEW" for inv in all_invoices)
rejected = sum(inv.decision == "REJECTED" for inv in all_invoices)

pages = {
    "Process invoices": "📤",
    "History & review": "📋",
    "Vendors & POs": "🏢",
    "Settings": "⚙️",
}
with st.sidebar:
    st.markdown("<div style='font-size:1.05rem;font-weight:750;color:#fff;padding:.35rem 0'>🧾  ZAMP <span style='color:#91a4c8;font-weight:500'>· Invoice desk</span></div>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;margin:.3rem 0 .55rem'>Workspace</p>", unsafe_allow_html=True)
    page = st.radio("Workspace navigation", list(pages), format_func=lambda item: f"{pages[item]}   {item}", label_visibility="collapsed")
    st.divider()
    st.caption("Demo workspace · session data")

st.markdown(f"""
<div class="hero">
  <div class="hero-kicker">Invoice operations · Demo workspace</div>
  <div class="hero-title">{pages[page]}&nbsp; {page}</div>
  <p class="hero-copy">Extract invoice details, match purchase orders, and review every decision in one place.</p>
</div>
""", unsafe_allow_html=True)
st.info("Privacy: PDFs are sent to Streamlit for processing and held in temporary session memory so you can retrieve them during this session. Do not upload confidential or regulated invoices.", icon="🔒")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Processed", total)
c2.metric("Approved", approved)
c3.metric("Needs review", review)
c4.metric("Rejected", rejected)

if page == "Process invoices":
    st.subheader("Upload invoice PDFs")
    uploads = st.file_uploader("Choose one or more PDF invoices (15 MB max each)", type=["pdf"], accept_multiple_files=True)
    if st.button("Process selected PDFs", type="primary", disabled=not uploads):
        with st.spinner("Extracting invoice fields and checking vendor, PO, duplicates, and totals…"):
            for item in uploads or []:
                try:
                    process_pdf(db, item.name, item.getvalue())
                except ValueError as exc:
                    st.error(f"{item.name}: {exc}")
        st.rerun()

    samples = sorted(SAMPLE_DIR.glob("*.pdf")) if SAMPLE_DIR.exists() else []
    if samples:
        st.subheader("Try a sample invoice")
        selected_sample = st.selectbox("Sample file", samples, format_func=lambda p: p.name)
        if st.button("Process sample PDF"):
            try:
                process_pdf(db, selected_sample.name, selected_sample.read_bytes())
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Processed invoices")
    st.caption("Your latest results appear here as soon as processing finishes. Download the original PDF from any row.")
    if all_invoices:
        st.dataframe([invoice_summary(inv) for inv in all_invoices], hide_index=True, width="stretch")
        for inv in all_invoices:
            data = inv.data or {}
            label = f"{inv.filename}  ·  {data.get('invoice_number') or 'No invoice number'}  ·  {inv.decision}"
            with st.expander(label):
                left, right = st.columns([3, 1])
                with left:
                    st.write(f"**Vendor:** {data.get('vendor_name') or 'Not detected'}")
                    st.write(f"**Invoice total:** {data.get('currency') or ''} {data.get('total_amount') if data.get('total_amount') is not None else 'Not detected'}")
                    st.write(f"**Extraction:** {inv.method or 'Not available'}")
                    for reason in (inv.result or {}).get("reasons", []):
                        st.write(f"• {reason}")
                pdf_bytes = st.session_state.get("processed_pdf_content", {}).get(inv.id)
                if pdf_bytes:
                    with right:
                        st.download_button("Download PDF", pdf_bytes, file_name=inv.filename, mime="application/pdf", key=f"process-download-{inv.id}", use_container_width=True)
    else:
        st.info("No invoices processed yet. Upload PDFs above or try a sample invoice to see results here.")

elif page == "History & review":
    st.subheader("Processing history")
    if all_invoices:
        st.dataframe([invoice_summary(inv) for inv in all_invoices], hide_index=True, width="stretch")
        for inv in all_invoices:
            data = inv.data or {}
            label = f"{inv.filename} · {data.get('invoice_number') or 'No invoice number'} · {inv.decision}"
            with st.expander(label):
                st.write("**Automated decision:**", inv.decision)
                st.write("**Extraction method:**", inv.method)
                st.write("**Extracted fields**")
                st.json({k: v for k, v in data.items() if k != "confidence"})
                if data.get("confidence"):
                    st.write("**Extraction confidence**")
                    st.json(data["confidence"])
                result = inv.result or {}
                st.write("**Decision explanation**")
                for reason in result.get("reasons", []):
                    st.write(f"- {reason}")
                st.write("**Validation checks**")
                st.dataframe(result.get("checks", []), hide_index=True, width="stretch")
                for warning in result.get("warnings", []):
                    st.warning(warning)
                st.info(result.get("recommended_action", "Review the validation details."))
                if inv.human_decision:
                    st.success(f"Human decision: {inv.human_decision} — {inv.review_notes or ''}")
                pdf_bytes = st.session_state.get("processed_pdf_content", {}).get(inv.id)
                if pdf_bytes:
                    st.download_button("Download original PDF", pdf_bytes, file_name=inv.filename, mime="application/pdf", key=f"history-download-{inv.id}")
                if inv.decision == "NEEDS_REVIEW":
                    with st.form(f"review-{inv.id}"):
                        st.markdown("**Record human review** (kept separate from the automated decision)")
                        reviewer = st.text_input("Reviewer name", key=f"reviewer-{inv.id}")
                        action = st.selectbox("Human decision", ["REJECTED", "APPROVED"], key=f"action-{inv.id}")
                        reason = st.text_input("Reason", key=f"reason-{inv.id}")
                        notes = st.text_area("Review notes", key=f"notes-{inv.id}")
                        if st.form_submit_button("Save human decision"):
                            if not reviewer.strip() or not reason.strip():
                                st.error("Enter the reviewer name and reason.")
                            else:
                                record_review(db, inv, reviewer.strip(), action, reason.strip(), notes.strip())
                                st.success("Human review recorded.")
                                st.rerun()
    else:
        st.info("No invoices processed in this browser session yet.")

elif page == "Vendors & POs":
    st.subheader("Vendor master")
    vendors = db.scalars(select(Vendor).order_by(Vendor.id)).all()
    st.dataframe([{"Vendor ID": v.id, "Name": v.name, "Approved": v.approved, "Currency": v.currency, "Email": v.email or ""} for v in vendors], hide_index=True, width="stretch")
    with st.form("new-vendor"):
        st.markdown("**Add vendor**")
        vendor_id = st.text_input("Vendor ID")
        vendor_name = st.text_input("Vendor name")
        vendor_currency = st.selectbox("Supported currency", ["INR", "USD", "EUR", "GBP"])
        vendor_approved = st.checkbox("Approved", value=True)
        if st.form_submit_button("Save vendor"):
            if not vendor_id.strip() or not vendor_name.strip():
                st.error("Vendor ID and name are required.")
            elif db.get(Vendor, vendor_id.strip()):
                st.error("That vendor ID already exists.")
            else:
                db.add(Vendor(id=vendor_id.strip(), name=vendor_name.strip(), currency=vendor_currency, approved=vendor_approved))
                db.commit(); st.rerun()

    st.subheader("Purchase orders")
    pos = db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.number)).all()
    st.dataframe([{"PO": p.number, "Vendor ID": p.vendor_id, "Currency": p.currency, "Amount": p.total_amount, "Previously invoiced": p.previously_invoiced, "Remaining": p.total_amount - p.previously_invoiced, "Status": p.status} for p in pos], hide_index=True, width="stretch")
    po_file = st.file_uploader("Import PO CSV", type=["csv"], key="po-csv")
    if po_file and st.button("Import CSV"):
        try:
            reader = csv.DictReader(io.StringIO(po_file.getvalue().decode("utf-8-sig")))
            if not reader.fieldnames:
                raise ValueError("The CSV has no header row.")
            headers = {h.strip().lower(): h for h in reader.fieldnames}
            required = {"po_number", "vendor_id", "currency", "total_amount"}
            if not required.issubset(headers):
                raise ValueError("Required headers: po_number,vendor_id,currency,total_amount.")
            imported = 0
            for row in reader:
                db.merge(PurchaseOrder(
                    number=row[headers["po_number"]].strip(), vendor_id=row[headers["vendor_id"]].strip(),
                    currency=row[headers["currency"]].strip().upper(), total_amount=float(row[headers["total_amount"]]),
                    previously_invoiced=float(row.get(headers.get("previously_invoiced", ""), 0) or 0),
                    status=row.get(headers.get("status", ""), "OPEN") or "OPEN",
                )); imported += 1
            db.commit(); st.success(f"Imported {imported} purchase orders."); st.rerun()
        except Exception as exc:
            db.rollback(); st.error(f"Could not import CSV: {exc}")

elif page == "Settings":
    st.subheader("Reconciliation settings")
    with st.form("settings"):
        tolerance_pct = st.number_input("PO amount tolerance (%)", min_value=0.0, max_value=100.0, value=setting(db, "amount_tolerance_percent", 2.0), step=0.5)
        tolerance_abs = st.number_input("Maximum absolute tolerance", min_value=0.0, value=setting(db, "amount_tolerance_absolute", 1000.0), step=100.0)
        rounding = st.number_input("Subtotal + tax rounding tolerance", min_value=0.0, value=setting(db, "rounding_tolerance", 1.0), step=0.5)
        if st.form_submit_button("Save settings"):
            for key, value in (("amount_tolerance_percent", tolerance_pct), ("amount_tolerance_absolute", tolerance_abs), ("rounding_tolerance", rounding)):
                saved = db.get(Setting, key) or Setting(key=key, value=float(value))
                saved.value = float(value); db.add(saved)
            db.commit(); st.success("Settings saved for this session.")

st.divider()
st.caption("Cloud demo data is isolated per browser session and is cleared when the session ends. Uploaded PDFs are processed from temporary files and are not added to the GitHub repository.")
