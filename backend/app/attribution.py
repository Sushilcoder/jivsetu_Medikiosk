"""Offline cryptographic attribution primitives for the demo API."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, uuid
from datetime import datetime, timezone
from typing import Any
from .db import connection, init_db
try:
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
 AESGCM=None
try:
 from pqcrypto.sign import ml_dsa_65 as _dsa
 from pqcrypto.kem import ml_kem_768 as _kem
 PQ_AVAILABLE=True
except ImportError:
 _dsa=_kem=None; PQ_AVAILABLE=False
ALGORITHMS={"signature":"ML-DSA-65" if PQ_AVAILABLE else "deterministic HMAC-SHA256 fallback (demo only)","kem":"ML-KEM-768" if PQ_AVAILABLE else "deterministic symmetric fallback (demo only)","encryption":"AES-256-GCM" if AESGCM else "unavailable","pq_available":PQ_AVAILABLE}
_fallback=secrets.token_bytes(32); _server_private=None
def _b(x): return base64.urlsafe_b64encode(x).decode()
def _u(x): return base64.urlsafe_b64decode(x.encode())
def _now(): return datetime.now(timezone.utc).isoformat()
def _canon(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def embed_watermark(document, watermark_id):
 bits="".join("\u200b" if bit == "0" else "\u200c" for byte in watermark_id.encode() for bit in f"{byte:08b}")
 return document + "\u2063" + bits + "\u2062"
def extract_watermark(document):
 if "\u2063" not in document or "\u2062" not in document: return None
 encoded=document.rsplit("\u2063",1)[1].split("\u2062",1)[0]
 if len(encoded) % 8 or any(char not in "\u200b\u200c" for char in encoded): return None
 try:
  return bytes(int("".join("0" if char == "\u200b" else "1" for char in encoded[i:i+8]),2) for i in range(0,len(encoded),8)).decode()
 except UnicodeDecodeError: return None
def _server_keys():
 global _server_private
 if _server_private is None:
  if PQ_AVAILABLE: _server_private, public=_dsa.keygen(); return _server_private,public
  _server_private=_fallback
 return _server_private,b"demo-fallback-public-key"
def _sign(data, private):
 return (_b(_dsa.sign(private,data)) if PQ_AVAILABLE else _b(hmac.new(private,data,hashlib.sha256).digest()))
def verify_signature(data,signature, recipient_id):
 row=_recipient(recipient_id)
 if not row: return False
 try: private=_u(row["signature_private_key"]); public=_u(row["signature_public_key"]); raw=_u(signature)
 except (ValueError, TypeError): return False
 if PQ_AVAILABLE:
   try:
    result=_dsa.verify(public,data,raw)
    return result is None or result is True
   except Exception: return False
 return hmac.compare_digest(hmac.new(private,data,hashlib.sha256).digest(),raw)
def register_recipient(recipient_id):
 init_db()
 if PQ_AVAILABLE:
   kp,ks=_kem.keygen(); sp,ss=_dsa.keygen()
 else: kp=ks=secrets.token_bytes(32); sp=b"demo-fallback-public-key"; ss=_fallback
 with connection() as c: c.execute("INSERT OR REPLACE INTO attribution_recipients VALUES (?,?,?,?,?,?,?)",(recipient_id,_b(kp),_b(ks),_b(sp),_b(ss),_now(),json.dumps(ALGORITHMS)))
 return {"recipient_id":recipient_id,"algorithms":ALGORITHMS,"kem_public_key":_b(kp),"signature_public_key":_b(sp)}
def _recipient(i):
 with connection() as c: return c.execute("SELECT * FROM attribution_recipients WHERE recipient_id=?",(i,)).fetchone()
def create_package(recipient_id,document,metadata=None):
 if AESGCM is None: raise RuntimeError("cryptography is required for AES-GCM demo")
 row=_recipient(recipient_id)
 if not row: raise KeyError("recipient not registered")
 key=AESGCM.generate_key(bit_length=256); nonce=os.urandom(12); metadata=metadata or {}; aad=_canon({"recipient_id":recipient_id,"metadata":metadata})
 ciphertext=AESGCM(key).encrypt(nonce,document.encode(),aad)
 encapsulated,shared=(_kem.encaps(_u(row["kem_public_key"])) if PQ_AVAILABLE else (hashlib.sha256(_u(row["kem_private_key"])+document.encode()).digest()[:16],None))
 if not PQ_AVAILABLE: shared=hashlib.sha256(_u(row["kem_private_key"])+encapsulated).digest()
 wn=os.urandom(12); wrapped=AESGCM(shared).encrypt(wn,key,recipient_id.encode()); pid=str(uuid.uuid4()); created=_now()
 with connection() as c: c.execute("INSERT INTO attribution_packages VALUES (?,?,?,?,?,?,?,?,?,?)",(pid,recipient_id,_b(nonce),_b(ciphertext),_b(encapsulated),_b(wn),_b(wrapped),json.dumps(metadata,sort_keys=True),created,json.dumps(ALGORITHMS)))
 return {"package_id":pid,"recipient_id":recipient_id,"metadata":metadata,"algorithms":ALGORITHMS,"created_at":created}
def decrypt_package(package_id,recipient_id):
 if AESGCM is None: raise RuntimeError("cryptography is required for AES-GCM demo")
 with connection() as c: package=c.execute("SELECT * FROM attribution_packages WHERE package_id=? AND recipient_id=?",(package_id,recipient_id)).fetchone()
 row=_recipient(recipient_id)
 if not package or not row: raise KeyError("package or recipient not found")
 enc=_u(package["encapsulated_key"]); shared=_kem.decaps(_u(row["kem_private_key"]),enc) if PQ_AVAILABLE else hashlib.sha256(_u(row["kem_private_key"])+enc).digest()
 key=AESGCM(shared).decrypt(_u(package["wrapped_nonce"]),_u(package["wrapped_key"]),recipient_id.encode()); metadata=json.loads(package["metadata"]); aad=_canon({"recipient_id":recipient_id,"metadata":metadata}); document=AESGCM(key).decrypt(_u(package["nonce"]),_u(package["ciphertext"]),aad).decode()
 event={"event_type":"document.decrypted","package_id":package_id,"recipient_id":recipient_id,"watermark_id":f"wm_{uuid.uuid4().hex}","document_sha256":hashlib.sha256(document.encode()).hexdigest(),"occurred_at":_now()}; receipt={"event":event,"signature":_sign(_canon(event),_u(row["signature_private_key"])),"signature_algorithm":ALGORITHMS["signature"],"signing_public_key":row["signature_public_key"],"algorithms":ALGORITHMS}; _append_ledger(receipt)
 return {"document":document,"watermarked_document":embed_watermark(document,event["watermark_id"]),"watermark_id":event["watermark_id"],"receipt":receipt}
def _append_ledger(receipt):
 with connection() as c:
  prev=c.execute("SELECT block_hash FROM attribution_ledger ORDER BY sequence DESC LIMIT 1").fetchone(); prev=prev[0] if prev else "0"*64; seq=c.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM attribution_ledger").fetchone()[0]; body={"sequence":seq,"previous_hash":prev,"receipt":receipt,"created_at":_now()}; digest=hashlib.sha256(_canon(body)).hexdigest(); c.execute("INSERT INTO attribution_ledger VALUES (?,?,?,?)",(seq,prev,json.dumps(body,sort_keys=True),digest))
def verify_watermark(watermark_id,signature=None):
 with connection() as c: row=c.execute("SELECT block FROM attribution_ledger WHERE json_extract(block,'$.receipt.event.watermark_id')=?",(watermark_id,)).fetchone()
 if not row:return {"valid":False,"reason":"watermark not found"}
 receipt=json.loads(row[0])["receipt"]; return {"valid":verify_signature(_canon(receipt["event"]),signature or receipt["signature"],receipt["event"]["recipient_id"]),"watermark_id":watermark_id,"receipt":receipt}
def verify_ledger():
 with connection() as c: rows=c.execute("SELECT * FROM attribution_ledger ORDER BY sequence").fetchall()
 prev="0"*64
 for r in rows:
  body=json.loads(r["block"])
  if body["previous_hash"]!=prev or hashlib.sha256(_canon(body)).hexdigest()!=r["block_hash"]: return {"valid":False,"checked_blocks":len(rows),"bad_sequence":r["sequence"]}
  prev=r["block_hash"]
 return {"valid":True,"checked_blocks":len(rows)}
