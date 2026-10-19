from .db import connection,init_db
def seed():
 init_db()
 with connection() as c:
  c.execute("INSERT OR IGNORE INTO patients VALUES (?,?,?,?,?)",("patient-001","Fictional Alex","hospital-a","1980-01-01","2025-01-01T00:00:00Z"));c.execute("INSERT OR IGNORE INTO patients VALUES (?,?,?,?,?)",("patient-002","Fictional Casey","hospital-b","1975-02-02","2025-01-01T00:00:00Z"))
  if c.execute("SELECT 1 FROM measurements WHERE patient_id=? LIMIT 1",("patient-001",)).fetchone(): return
  for metric,unit,vals in [("HbA1c","%",[7.8,7.2,6.9]),("weight","mg/dL",[130,128,126])]:
   for i,v in enumerate(vals):c.execute("INSERT INTO measurements(patient_id,metric,value,unit,measured_at,recorded_by) VALUES(?,?,?,?,?,?)",("patient-001",metric,v,unit,f"2025-0{i+1}-01T00:00:00Z","seed"))
if __name__=="__main__":seed()
