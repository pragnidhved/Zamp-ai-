import hashlib, csv, io, logging
from pathlib import Path
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from .db import Base, engine, get_db
from .config import UPLOADS, MAX_UPLOAD
from .models import Vendor, PurchaseOrder, Invoice, Review, Setting
from .services.pdf_extractor import extract_pdf
from .services.parser import parse_invoice
from .services.reconciliation import reconcile

Base.metadata.create_all(engine)
app=FastAPI(title="Invoice Reconciliation", version="1.0")
logging.basicConfig(level=logging.INFO)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_methods=["*"],allow_headers=["*"])

def serialize(i): return {"id":i.id,"filename":i.filename,"created_at":i.created_at,"method":i.method,"data":i.data,"decision":i.decision,"result":i.result,"human_decision":i.human_decision,"review_notes":i.review_notes}

def process(db, inv):
    was_approved = inv.decision == "APPROVED"
    try:
        text,method,warnings=extract_pdf(inv.path)
        data=parse_invoice(text); result=reconcile(db,data,inv.file_hash,inv.id); result["warnings"].extend(warnings)
        inv.method=method; inv.extracted_text=text[:50000]; inv.data=data; inv.decision=result["decision"]; inv.result=result
        if inv.decision=="APPROVED" and not was_approved and result.get("po_number"):
            po=db.get(PurchaseOrder,result["po_number"]); po.previously_invoiced += data["total_amount"]
        db.commit(); db.refresh(inv)
    except Exception as e:
        logging.exception("Invoice processing failed for record %s",inv.id)
        db.rollback(); inv=db.get(Invoice,inv.id); inv.decision="NEEDS_REVIEW"; inv.result={"decision":"NEEDS_REVIEW","checks":[],"reasons":["PDF processing failed. Check that the file is readable and retry."],"warnings":[],"recommended_action":"Check the PDF and retry."}; db.commit()
    return inv

@app.get("/api/health")
def health(): return {"status":"ok"}
@app.post("/api/invoices/upload")
async def upload(files:list[UploadFile]=File(...),db:Session=Depends(get_db)):
    output=[]
    for f in files:
        if not f.filename.lower().endswith(".pdf"): raise HTTPException(415,"Only PDF files are accepted.")
        content=await f.read(MAX_UPLOAD+1)
        if len(content)>MAX_UPLOAD: raise HTTPException(413,"File exceeds 15 MB.")
        if not content.startswith(b"%PDF-"): raise HTTPException(400,"File does not have a valid PDF signature.")
        digest=hashlib.sha256(content).hexdigest(); safe=Path(f.filename).name
        target=UPLOADS/(digest+".pdf"); target.write_bytes(content)
        inv=Invoice(filename=safe,path=str(target),file_hash=digest); db.add(inv); db.commit(); db.refresh(inv)
        output.append(serialize(process(db,inv)))
    return {"items":output}
@app.post("/api/invoices/batch-process")
def batch(body:dict,db:Session=Depends(get_db)):
    items=[]
    for iid in body.get("invoice_ids",[]):
        inv=db.get(Invoice,int(iid))
        if inv: items.append(serialize(process(db,inv)))
    return {"items":items}
@app.post("/api/invoices/{iid}/process")
def process_one(iid:int,db:Session=Depends(get_db)):
    inv=db.get(Invoice,iid)
    if not inv: raise HTTPException(404,"Invoice not found.")
    return serialize(process(db,inv))
@app.get("/api/invoices")
def invoices(db:Session=Depends(get_db)):
    return {"items":[serialize(i) for i in db.scalars(select(Invoice).order_by(Invoice.id.desc())).all()]}
@app.get("/api/invoices/{iid}")
def invoice(iid:int,db:Session=Depends(get_db)):
    inv=db.get(Invoice,iid)
    if not inv: raise HTTPException(404,"Invoice not found.")
    return serialize(inv)
@app.get("/api/invoices/{iid}/progress")
def progress(iid:int,db:Session=Depends(get_db)):
    inv=db.get(Invoice,iid)
    if not inv: raise HTTPException(404,"Invoice not found.")
    return {"id":iid,"status":inv.decision,"stages":[{"name":n,"status":"complete"} for n in ["PDF extraction","Field parsing","Vendor and PO checks","Decision and audit"]]}
@app.get("/api/invoices/{iid}/file")
def invoice_file(iid:int,db:Session=Depends(get_db)):
    from fastapi.responses import FileResponse
    inv=db.get(Invoice,iid)
    if not inv or not Path(inv.path).is_file(): raise HTTPException(404,"File not found.")
    return FileResponse(inv.path,media_type="application/pdf",filename=inv.filename)
@app.get("/api/dashboard/summary")
def summary(db:Session=Depends(get_db)):
    return {"total":db.scalar(select(func.count(Invoice.id))) or 0,"approved":db.scalar(select(func.count(Invoice.id)).where(Invoice.decision=="APPROVED")) or 0,"rejected":db.scalar(select(func.count(Invoice.id)).where(Invoice.decision=="REJECTED")) or 0,"review":db.scalar(select(func.count(Invoice.id)).where(Invoice.decision=="NEEDS_REVIEW")) or 0}
@app.get("/api/dashboard/trends")
def trends(db:Session=Depends(get_db)):
    return {"items":[{"decision":d,"count":n} for d,n in db.execute(select(Invoice.decision,func.count()).group_by(Invoice.decision)).all()]}
@app.get("/api/vendors")
def vendors(db:Session=Depends(get_db)):
    return {"items":[{"id":v.id,"name":v.name,"approved":v.approved,"currency":v.currency,"email":v.email} for v in db.scalars(select(Vendor)).all()]}
@app.post("/api/vendors")
def add_vendor(body:dict,db:Session=Depends(get_db)):
    if not body.get("id") or not body.get("name"): raise HTTPException(422,"Vendor id and name are required.")
    v=Vendor(id=body["id"],name=body["name"],approved=bool(body.get("approved",True)),currency=body.get("currency","INR"),email=body.get("email")); db.add(v)
    try: db.commit()
    except Exception: db.rollback(); raise HTTPException(409,"Vendor id already exists.")
    return {"id":v.id,"name":v.name}
@app.put("/api/vendors/{vid}")
def update_vendor(vid:str,body:dict,db:Session=Depends(get_db)):
    v=db.get(Vendor,vid)
    if not v: raise HTTPException(404,"Vendor not found.")
    for k in ("name","approved","currency","email"):
        if k in body: setattr(v,k,body[k])
    db.commit(); return {"id":v.id,"name":v.name,"approved":v.approved}
@app.get("/api/purchase-orders")
def pos(db:Session=Depends(get_db)):
    return {"items":[{"number":p.number,"vendor_id":p.vendor_id,"currency":p.currency,"total_amount":p.total_amount,"previously_invoiced":p.previously_invoiced,"remaining":p.total_amount-p.previously_invoiced,"status":p.status} for p in db.scalars(select(PurchaseOrder)).all()]}
@app.post("/api/purchase-orders")
def add_po(body:dict,db:Session=Depends(get_db)):
    p=PurchaseOrder(number=body["number"],vendor_id=body["vendor_id"],currency=body.get("currency","INR"),total_amount=float(body["total_amount"]),previously_invoiced=float(body.get("previously_invoiced",0)),status=body.get("status","OPEN")); db.add(p); db.commit(); return {"number":p.number}
@app.post("/api/purchase-orders/import")
async def import_pos(file:UploadFile=File(...),db:Session=Depends(get_db)):
    raw=(await file.read()).decode("utf-8-sig")
    reader=csv.DictReader(io.StringIO(raw)); required={"po_number","vendor_id","currency","total_amount"}
    if not reader.fieldnames or not required.issubset({h.strip().lower() for h in reader.fieldnames}): raise HTTPException(400,"CSV requires po_number,vendor_id,currency,total_amount headers.")
    names={h.strip().lower():h for h in reader.fieldnames}; count=0
    try:
        for row in reader:
            p=PurchaseOrder(number=row[names["po_number"]],vendor_id=row[names["vendor_id"]],currency=row[names["currency"]],total_amount=float(row[names["total_amount"]]),previously_invoiced=float(row.get(names.get("previously_invoiced",""),0) or 0),status=row.get(names.get("status",""),"OPEN") or "OPEN")
            db.merge(p); count+=1
        db.commit()
    except Exception as e: db.rollback(); raise HTTPException(400,"Invalid PO CSV row: "+str(e)[:180])
    return {"imported":count}
@app.get("/api/settings")
def settings(db:Session=Depends(get_db)):
    defaults={"amount_tolerance_percent":2.0,"amount_tolerance_absolute":1000.0,"rounding_tolerance":1.0}
    return {**defaults,**{s.key:s.value for s in db.scalars(select(Setting)).all()}}
@app.put("/api/settings")
def update_settings(body:dict,db:Session=Depends(get_db)):
    for k,v in body.items():
        if k not in {"amount_tolerance_percent","amount_tolerance_absolute","rounding_tolerance"} or float(v)<0: raise HTTPException(422,"Unknown setting or negative value.")
        s=db.get(Setting,k) or Setting(key=k,value=float(v)); s.value=float(v); db.add(s)
    db.commit(); return settings(db)
@app.get("/api/reviews")
def reviews(db:Session=Depends(get_db)):
    return {"items":[{"id":r.id,"invoice_id":r.invoice_id,"reviewer":r.reviewer,"action":r.action,"reason":r.reason,"notes":r.notes,"created_at":r.created_at} for r in db.scalars(select(Review).order_by(Review.id.desc())).all()]}
@app.post("/api/invoices/{iid}/review")
def review(iid:int,body:dict,db:Session=Depends(get_db)):
    inv=db.get(Invoice,iid)
    if not inv: raise HTTPException(404,"Invoice not found.")
    action=body.get("action")
    if action not in {"APPROVED","REJECTED"}: raise HTTPException(422,"Action must be APPROVED or REJECTED.")
    r=Review(invoice_id=iid,reviewer=body.get("reviewer","Local reviewer"),action=action,reason=body.get("reason","Human review"),notes=body.get("notes","")); db.add(r)
    inv.human_decision=action; inv.review_notes=r.reason+ (" — "+r.notes if r.notes else ""); db.commit(); return serialize(inv)
