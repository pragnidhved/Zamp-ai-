from app.db import Base,engine,SessionLocal
from app.models import Vendor,PurchaseOrder,Setting
Base.metadata.create_all(engine); db=SessionLocal()
vs=[("V001","ABC Technologies",True,"INR"),("V002","XYZ Solutions",True,"INR"),("V003","Global Supplies",True,"INR"),("V004","Unknown Traders",False,"INR"),("V005","Northwind Services",True,"USD")]
for i,n,a,c in vs: db.merge(Vendor(id=i,name=n,approved=a,currency=c))
for i in range(1,11):
 v=vs[(i-1)%5]; db.merge(PurchaseOrder(number=f"PO-{1000+i}",vendor_id=v[0],currency=v[3],total_amount=25000+i*5000,previously_invoiced=5000 if i%3==0 else 0,status="OPEN"))
for k,v in [("amount_tolerance_percent",2.0),("amount_tolerance_absolute",1000.0),("rounding_tolerance",1.0)]: db.merge(Setting(key=k,value=v))
db.commit();db.close();print("Seeded 5 vendors and 10 purchase orders.")
