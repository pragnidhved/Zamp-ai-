from difflib import SequenceMatcher
from sqlalchemy import select
from ..models import Vendor,PurchaseOrder,Invoice,Setting
def norm(s): return " ".join("".join(c.lower() if c.isalnum() else " " for c in s).split())
def reconcile(db,data,file_hash,current_id=None):
    checks=[]; reasons=[]; warnings=[]
    def check(name,passed,detail,hard=False):
        checks.append({"name":name,"passed":bool(passed),"detail":detail,"hard":hard})
        if not passed: reasons.append(detail)
    dup=db.scalar(select(Invoice).where(Invoice.file_hash==file_hash,Invoice.id!=(current_id or -1)))
    iddup=None
    for old in db.scalars(select(Invoice).where(Invoice.id!=(current_id or -1))).all():
        if data.get("invoice_number") and old.data.get("invoice_number")==data["invoice_number"] and norm(old.data.get("vendor_name") or "")==norm(data.get("vendor_name") or ""):
            iddup=old; break
    check("duplicate",not(dup or iddup),"Previously processed invoice detected." if dup or iddup else "No exact duplicate found.",True)
    vendor=None
    if data.get("vendor_name"):
        ranked=sorted(((SequenceMatcher(None,norm(data["vendor_name"]),norm(v.name)).ratio(),v) for v in db.scalars(select(Vendor)).all()),key=lambda x:x[0],reverse=True)
        if ranked and (ranked[0][0]==1 or ranked[0][0]>=.90 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.08)): vendor=ranked[0][1]
    check("vendor",bool(vendor and vendor.approved),"Vendor verified and approved." if vendor and vendor.approved else "Vendor is unknown, ambiguous, or unapproved.")
    po=None
    if data.get("po_number"):
        key=data["po_number"].upper().replace(" ","")
        po=next((p for p in db.scalars(select(PurchaseOrder)).all() if p.number.upper().replace(" ","")==key),None)
    elif vendor and data.get("total_amount") is not None:
        cand=[p for p in db.scalars(select(PurchaseOrder).where(PurchaseOrder.vendor_id==vendor.id)).all() if p.currency==data.get("currency") and abs(p.total_amount-p.previously_invoiced-data["total_amount"])<=max(1,p.total_amount*.02)]
        if len(cand)==1: po=cand[0]
        elif cand: warnings.append("Multiple purchase orders could match; provide an explicit PO reference.")
    check("purchase_order",bool(po),"Purchase order matched." if po else "Purchase order is missing, unmatched, or ambiguous.")
    if po:
        check("po_vendor",bool(vendor and po.vendor_id==vendor.id),"PO vendor matches." if vendor and po.vendor_id==vendor.id else "PO belongs to a different vendor.")
        check("currency",bool(data.get("currency") and po.currency==data["currency"]),"Invoice and PO currency match." if data.get("currency")==po.currency else "Invoice and PO currencies differ or currency is missing.")
        check("po_status",po.status.upper()=="OPEN",f"PO status is {po.status}.",po.status.upper() in {"CANCELLED","CLOSED"})
        rem=po.total_amount-po.previously_invoiced; s=db.get(Setting,"amount_tolerance_percent"); a=db.get(Setting,"amount_tolerance_absolute")
        tol=min(a.value if a else 1000,rem*(s.value if s else 2)/100); total=data.get("total_amount")
        check("po_balance",total is not None and total<=rem+tol,f"Invoice total {total} vs remaining PO balance {rem:.2f} (tolerance {tol:.2f}).")
    total=data.get("total_amount"); sub=data.get("subtotal"); tax=data.get("tax_amount")
    round_setting=db.get(Setting,"rounding_tolerance")
    rounding=round_setting.value if round_setting else 1.0
    present=total is not None and sub is not None and tax is not None
    ok=present and abs(sub+tax-total)<=rounding
    hard_invalid=present and not ok
    detail="Subtotal plus tax equals total." if ok else f"Subtotal, tax, and total are missing or do not reconcile within {rounding:.2f}."
    check("arithmetic",ok,detail,hard_invalid)
    missing=[k for k in ("invoice_number","vendor_name","total_amount") if not data.get(k)]
    check("required_fields",not missing,"Critical fields present." if not missing else "Missing critical fields: "+", ".join(missing)+".")
    low=[k for k,v in data.get("confidence",{}).items() if k in {"invoice_number","vendor_name","total_amount"} and v<.7]
    check("extraction_confidence",not low,"Critical extraction confidence is adequate." if not low else "Low extraction confidence: "+", ".join(low)+".")
    if dup or iddup: decision="REJECTED"
    elif any(not c["passed"] and c["hard"] for c in checks): decision="REJECTED"
    elif all(c["passed"] for c in checks): decision="APPROVED"
    else: decision="NEEDS_REVIEW"
    return {"decision":decision,"checks":checks,"reasons":reasons,"warnings":warnings,"vendor_id":vendor.id if vendor else None,"po_number":po.number if po else None,"recommended_action":"Pay invoice after normal controls." if decision=="APPROVED" else "Reject the confirmed duplicate or invalid arithmetic." if decision=="REJECTED" else "Have AP/procurement verify the flagged fields and PO balance."}
