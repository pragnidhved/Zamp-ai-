import re
from datetime import datetime
def cap(pattern,text,flags=re.I):
    m=re.search(pattern,text,flags); return m.group(1).strip(" :#\t") if m else None
def parse_invoice(text):
    number=cap(r"(?:invoice\s*(?:no\.?|number|#)|bill\s*no\.?|reference\s*number)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]{2,})",text)
    vendor=cap(r"(?:vendor|supplier|from)\s*[:\-]\s*([^\n]+)",text)
    po=cap(r"(?:purchase\s*order|PO)\s*(?:no\.?|number|#)?\s*[:#-]?\s*(PO[- ]?[A-Z0-9-]+)",text)
    date=cap(r"(?:invoice\s*date|date)\s*[:\-]?\s*(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})",text)
    amounts={}
    for k,lbl in {"subtotal":"subtotal|sub-total","tax_amount":"tax|GST|VAT","total_amount":"grand total|total due|invoice total|total"}.items():
        v=cap(r"^\s*(?:"+lbl+r")\s*[:\-]?\s*(?:INR|Rs\.?|₹|USD|\$)?\s*([\d,]+(?:\.\d{1,2})?)",text,re.I|re.M)
        try: amounts[k]=float(v.replace(",","")) if v else None
        except ValueError: amounts[k]=None
    currency="USD" if re.search(r"\bUSD\b|\$",text) else "INR" if re.search(r"INR|Rs\.?|₹",text,re.I) else None
    try:
        if date: date=datetime.strptime(date,"%d/%m/%Y").date().isoformat() if len(date.split("/")[0])<=2 else date
    except ValueError: pass
    return {"invoice_number":number,"vendor_name":vendor,"po_number":po,"invoice_date":date,"currency":currency,**amounts,"line_items":[],"confidence":{"invoice_number":.96 if number else 0,"vendor_name":.85 if vendor else 0,"po_number":.96 if po else 0,"total_amount":.95 if amounts["total_amount"] is not None else 0}}
