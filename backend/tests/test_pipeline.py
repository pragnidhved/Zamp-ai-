from pathlib import Path
import pymupdf as fitz
from fastapi.testclient import TestClient
from app.main import app
from app.services.parser import parse_invoice

def test_parser_extracts_fields():
    parsed=parse_invoice("Vendor: ABC Technologies\nInvoice Number: INV-123\nPO Number: PO-1001\nCurrency: INR\nSubtotal: 100.00\nTax: 18.00\nGrand Total: 118.00")
    assert parsed["invoice_number"]=="INV-123"
    assert parsed["vendor_name"]=="ABC Technologies"
    assert parsed["total_amount"]==118

def test_upload_rejects_non_pdf():
    client=TestClient(app)
    response=client.post("/api/invoices/upload",files={"files":("fake.pdf",b"not a pdf","application/pdf")})
    assert response.status_code==400

def test_upload_pdf_is_persisted():
    client=TestClient(app)
    doc=fitz.open(); page=doc.new_page(); page.insert_text((60,60),"Vendor: ABC Technologies\nInvoice Number: TEST-9001\nPO Number: PO-1001\nCurrency: INR\nSubtotal: 100.00\nTax: 18.00\nGrand Total: 118.00")
    data=doc.tobytes(); doc.close()
    response=client.post("/api/invoices/upload",files={"files":("test-invoice.pdf",data,"application/pdf")})
    assert response.status_code==200
    result=response.json()["items"][0]
    assert result["data"]["invoice_number"]=="TEST-9001"
    assert result["decision"] in {"APPROVED","NEEDS_REVIEW","REJECTED"}
    assert client.get(f"/api/invoices/{result['id']}").status_code==200
