"""Create reproducible machine-readable sample invoice PDFs under sample_data/invoices."""
from pathlib import Path
import pymupdf as fitz
ROOT=Path(__file__).resolve().parents[1]/"sample_data"/"invoices"
ROOT.mkdir(parents=True,exist_ok=True)
cases=[]
for i in range(1,16):
    vendor=[("V001","ABC Technologies","INR"),("V002","XYZ Solutions","INR"),("V003","Global Supplies","INR"),("V004","Unknown Traders","INR"),("V005","Northwind Services","USD")][(i-1)%5]
    po=f"PO-{1000+i}"
    inv=f"SAMPLE-{2026}-{i:03d}"
    subtotal=10000+i*250
    tax=round(subtotal*.18,2)
    total=round(subtotal+tax,2)
    ref=po
    if i==5: ref="" # missing PO -> review
    if i==6: vendor=("VX99","Unlisted Trading House","INR")
    if i==7: tax=5.0 # arithmetic issue
    if i==8:
        vendor=("V005","Northwind Services","USD"); po="PO-1005"; ref=po
        inv="SAMPLE-2026-008-CURRENCY"
    if i==9: total=1000.0; subtotal=847.46; tax=152.54 # partial bill example
    if i==10: total=99000.0; subtotal=83898.31; tax=15101.69 # exceeds balance
    if i==4: total=50000.0; subtotal=42372.88; tax=7627.12 # high amount
    invoice_currency="INR" if i==8 else vendor[2]
    text=f"{vendor[1]}\nInvoice Number: {inv}\nInvoice Date: 06/11/2026\nVendor: {vendor[1]}\nPO Number: {ref}\nCurrency: {invoice_currency}\nSubtotal: {subtotal:.2f}\nTax: {tax:.2f}\nGrand Total: {total:.2f}\n\nDescription           Qty   Unit Price   Line Total\nConsulting services    1    {subtotal:.2f}      {subtotal:.2f}\n"
    doc=fitz.open(); page=doc.new_page(width=595,height=842)
    page.insert_textbox(fitz.Rect(55,55,540,500),text,fontsize=12,fontname="helv",lineheight=1.5)
    if i==2:
        pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
        scanned=fitz.open(); image_page=scanned.new_page(width=595,height=842); image_page.insert_image(image_page.rect,pixmap=pix)
        doc.close(); doc=scanned
    out=ROOT/f"invoice_{i:02d}.pdf"; doc.save(out); doc.close(); cases.append(out)
# An exact byte-for-byte duplicate for duplicate detection demonstration.
(ROOT/"invoice_03_duplicate.pdf").write_bytes((ROOT/"invoice_03.pdf").read_bytes())
print(f"Generated {len(cases)+1} PDF invoices in {ROOT}")
