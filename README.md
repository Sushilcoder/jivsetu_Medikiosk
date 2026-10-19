# CipherTrace / Provenance Vault

CipherTrace is an offline-first proof of concept for cryptographic attribution of multi-recipient encrypted documents. It demonstrates a complete local flow: encrypt once, decrypt for a recipient, mint a unique invisible watermark identifier at decryption time, sign the event with that recipient's private post-quantum signing key, append it to a hash-chained ledger, and verify a leaked watermark back to a recipient.

## What is implemented

- **Document distribution:** AES-256-GCM encrypts the document; ML-KEM-768 wraps the per-document key for the selected recipient.
- **Recipient identity:** locally generated ML-KEM-768 and ML-DSA-65 key pairs are stored in SQLite for this demo.
- **Decryption provenance:** each decryption creates a fresh `wm_<uuid>` watermark/session identifier and hashes the decrypted content.
- **Non-repudiation:** the decryption record is signed with the recipient's ML-DSA-65 private key. The matching public key is included in the receipt for independent verification.
- **Immutable audit layer:** an append-only SQLite ledger stores SHA-256-linked blocks. Tampering with a prior block breaks chain verification.
- **Leak investigation:** submit a watermark ID and optional receipt signature to resolve and verify the original recipient and event.
- **Air-gapped operation:** all operations are local. There is no cloud KMS, public blockchain, or external service dependency.

The frontend is a dependency-free static dashboard in `frontend/`. The API is FastAPI in `backend/`. The `pqcrypto` package supplies the NIST-standardized ML-KEM-768 and ML-DSA-65 implementations. If it is unavailable, the API reports a clearly labeled demo fallback rather than silently claiming post-quantum security.

## Run locally

Requires Python 3.11 (also pinned in `.python-version`).

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -r requirements.lock
cp .env.example .env  # Windows: copy .env.example .env
uvicorn app.main:app --app-dir backend --reload
```

In another terminal, serve the UI so browser requests are allowed:

```bash
python -m http.server 4173 --directory frontend
```

Open <http://localhost:4173>. Click **Run demo workflow** to seed a roster, create an encrypted package, decrypt it, mint a signed receipt, and verify the ledger. The API docs are at <http://localhost:8000/docs>.

## Test

```bash
pytest -q
node --check frontend/app.js
```

The tests cover AES-GCM/KEM round trips, unique watermarks, recipient signatures, malformed signatures, ledger tamper detection, and the existing API isolation/trend behavior.

## Docker

```bash
docker build -t ciphertrace .
docker run --rm -p 8000:8000 -v ciphertrace-data:/app/data ciphertrace
```

Serve `frontend/` locally or from the same offline machine and point `window.CIPHERTRACE_API` at the container if needed. The Docker image contains the pinned runtime dependencies and does not need internet access after it is built.

## Security boundaries

This is a self-contained demonstrator, not a production DRM or forensic watermarking system. The current UI watermark is a forensic session token carried in the signed provenance record; true robust invisible media watermarking requires format-specific codecs and extraction/attack-resistance testing. SQLite is a local single-node ledger; a production deployment should use independent offline validator nodes and protected recipient key storage. Demo identities and keys are generated locally and are not a replacement for an enterprise identity provider or hardware-backed key custody.
