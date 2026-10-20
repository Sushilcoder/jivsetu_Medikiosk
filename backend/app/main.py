import json,os
from datetime import datetime,timezone
from typing import Optional
from fastapi import FastAPI,Depends,Header,HTTPException,Request
from pydantic import BaseModel,Field
from .db import connection,init_db
from .trends import calculate_trend
from . import attribution
app=FastAPI(title="Longitudinal Patient Health Monitoring API",version="1.0.0")
def now():return datetime.now(timezone.utc).isoformat()
@app.on_event("startup")
def startup():
 init_db()
 if os.getenv("SEED_DEMO")=="1":
  from .seed import seed;seed()
def actor(x_demo_user:Optional[str]=Header(None),x_demo_role:Optional[str]=Header(None),x_demo_hospital:Optional[str]=Header(None)):
 user=x_demo_user or "patient-001"; role=(x_demo_role or ("patient" if user.startswith("patient") else "doctor")).lower()
 if role not in {"patient","doctor"}:raise HTTPException(401,"invalid demo role")
 return {"id":user,"role":role,"hospital_id":x_demo_hospital or "hospital-a"}
def patient_or_404(c,pid):
 p=c.execute("SELECT * FROM patients WHERE id=?",(pid,)).fetchone()
 if not p:raise HTTPException(404,"patient not found")
 return p
def authorize(c,pid,a,doctor=False):
 p=patient_or_404(c,pid)
 if a["role"]=="patient" and a["id"]!=pid:raise HTTPException(403,"patient access is limited to their own record")
 if doctor and a["role"]!="doctor":raise HTTPException(403,"doctor role required")
 if a["role"]=="doctor" and a["hospital_id"]!=p["hospital_id"]:raise HTTPException(403,"hospital access denied")
 return p
def ser(r):return dict(r)
@app.get("/health")
def health():
 with connection() as c:c.execute("SELECT 1")
 return {"status":"ok"}
@app.get("/patients/{patient_id}/dashboard")
def dashboard(patient_id:str,a=Depends(actor)):
 with connection() as c:
  p=authorize(c,patient_id,a); rows=c.execute("SELECT * FROM measurements WHERE patient_id=? ORDER BY measured_at",(patient_id,)).fetchall(); grouped={}
  for r in rows:grouped.setdefault(r["metric"],[]).append(dict(r))
  return {"patient":ser(p),"latest_measurements":{m:v[-1] for m,v in grouped.items()},"trends":{m:calculate_trend(v,m) for m,v in grouped.items()}}
@app.get("/patients/{patient_id}/measurements")
def measurements(patient_id:str,metric:Optional[str]=None,a=Depends(actor)):
 with connection() as c:
  authorize(c,patient_id,a);q="SELECT * FROM measurements WHERE patient_id=?";args=[patient_id]
  if metric:q+=" AND metric=?";args.append(metric)
  q+=" ORDER BY measured_at"
  return {"measurements":[ser(r) for r in c.execute(q,args)]}
@app.get("/patients/{patient_id}/reports")
def reports(patient_id:str,a=Depends(actor)):
 with connection() as c:
  authorize(c,patient_id,a);return {"reports":[ser(r) for r in c.execute("SELECT * FROM reports WHERE patient_id=? ORDER BY uploaded_at DESC",(patient_id,))]}
@app.post("/patients/{patient_id}/reports",status_code=201)
async def upload_report(patient_id:str,request:Request,a=Depends(actor)):
 # JSON metadata is always supported; multipart is accepted when python-multipart is installed.
 content_type=request.headers.get("content-type",""); filename="report"; notes=""; file_type=None
 if content_type.startswith("application/json"):
  data=await request.json(); filename=data.get("filename",filename); notes=data.get("notes",""); file_type=data.get("content_type")
 else:
  try:
   form=await request.form(); filename=form.get("filename",filename); notes=form.get("notes",""); uploaded=form.get("file"); file_type=getattr(uploaded,"content_type",None); filename=getattr(uploaded,"filename",filename) or filename
  except Exception as exc:
   raise HTTPException(415,"use JSON metadata or install python-multipart for multipart uploads") from exc
 with connection() as c:
  authorize(c,patient_id,a);cur=c.execute("INSERT INTO reports(patient_id,filename,content_type,uploaded_by,uploaded_at,notes) VALUES(?,?,?,?,?,?)",(patient_id,filename,file_type,a["id"],now(),notes));return {"report":ser(c.execute("SELECT * FROM reports WHERE id=?",(cur.lastrowid,)).fetchone())}
class Correction(BaseModel):
 measurement_id:int;value:float;unit:str;reason:str=Field(min_length=1)
@app.post("/patients/{patient_id}/measurements/correction")
def correction(patient_id:str,body:Correction,a=Depends(actor)):
 with connection() as c:
  authorize(c,patient_id,a,doctor=True);old=c.execute("SELECT * FROM measurements WHERE id=? AND patient_id=?",(body.measurement_id,patient_id)).fetchone()
  if not old:raise HTTPException(404,"measurement not found")
  c.execute("UPDATE measurements SET value=?,unit=?,recorded_by=? WHERE id=?",(body.value,body.unit,a["id"],body.measurement_id));details=json.dumps({"measurement_id":body.measurement_id,"old_value":old["value"],"new_value":body.value,"reason":body.reason});c.execute("INSERT INTO audit_events(actor_id,actor_role,action,patient_id,details,created_at) VALUES(?,?,?,?,?,?)",(a["id"],a["role"],"measurement.corrected",patient_id,details,now()));return {"measurement":ser(c.execute("SELECT * FROM measurements WHERE id=?",(body.measurement_id,)).fetchone()),"audit_recorded":True}

class Recipient(BaseModel): recipient_id:str=Field(min_length=1)
class Package(BaseModel): recipient_id:str; document:str; metadata:dict={}
class DecryptRequest(BaseModel): recipient_id:str
class VerifyRequest(BaseModel): watermark_id:Optional[str]=None; leaked_document:Optional[str]=None; signature:Optional[str]=None
@app.post("/attribution/recipients",status_code=201)
def register_recipient(body:Recipient): return attribution.register_recipient(body.recipient_id)
@app.post("/attribution/recipients/{recipient_id}/demo-key",status_code=201)
def demo_key(recipient_id:str): return attribution.register_recipient(recipient_id)
@app.post("/attribution/packages",status_code=201)
@app.post("/attribution/documents",status_code=201,include_in_schema=False)
def create_package(body:Package):
 try:return attribution.create_package(body.recipient_id,body.document,body.metadata)
 except KeyError as e:raise HTTPException(404,str(e))
@app.post("/attribution/packages/{package_id}/decrypt")
@app.post("/attribution/documents/{package_id}/decrypt",include_in_schema=False)
def decrypt(package_id:str,body:DecryptRequest):
 try:return attribution.decrypt_package(package_id,body.recipient_id)
 except KeyError as e:raise HTTPException(404,str(e))
 except Exception as e:raise HTTPException(400,"decryption failed") from e
@app.post("/attribution/verify")
@app.post("/attribution/watermarks/verify",include_in_schema=False)
def verify(body:VerifyRequest):
 watermark_id=body.watermark_id or attribution.extract_watermark(body.leaked_document or "")
 if not watermark_id: return {"valid":False,"reason":"no embedded watermark found"}
 return attribution.verify_watermark(watermark_id,body.signature)
@app.get("/attribution/ledger/verify")
def ledger_verify():return attribution.verify_ledger()

from pathlib import Path
from fastapi.staticfiles import StaticFiles
FRONTEND_DIR=Path(__file__).resolve().parents[2]/"frontend"
if FRONTEND_DIR.is_dir():
 app.mount("/",StaticFiles(directory=FRONTEND_DIR,html=True),name="frontend")
