"""Private Supabase Storage synchronization for Strud's canonical textbook.

Only the backend reads SUPABASE_SERVICE_ROLE_KEY.  The bucket/object are
never exposed to the browser and all writes are explicit administrator jobs.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import requests

from config import CACHE_DIR, CLOUD_KB_ENABLED, PDF_FILE

BUCKET = os.environ.get("STRUD_KB_BUCKET", "strud-knowledge-base").strip()
OBJECT = os.environ.get("STRUD_KB_OBJECT", "biology/Biology_ResourceBook.pdf").strip()
_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def configured() -> bool:
    return CLOUD_KB_ENABLED and bool(_URL and _KEY)


def _headers(content_type: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_KEY}", "apikey": _KEY}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_private_bucket() -> None:
    response = requests.post(
        f"{_URL}/storage/v1/bucket",
        headers=_headers("application/json"),
        json={"id": BUCKET, "name": BUCKET, "public": False, "file_size_limit": 25 * 1024 * 1024},
    )
    if response.status_code not in (200, 201, 409):
        raise RuntimeError(f"Could not create/check knowledge-base bucket ({response.status_code}).")


def upload_canonical_source(source: Path) -> dict[str, object]:
    if not configured():
        raise RuntimeError("Cloud knowledge-base storage is not configured.")
    if not source.is_file():
        raise RuntimeError("Canonical Biology resource book is not available on this host.")
    ensure_private_bucket()
    with source.open("rb") as handle:
        response = requests.post(
            f"{_URL}/storage/v1/object/{BUCKET}/{OBJECT}",
            headers={**_headers("application/pdf"), "x-upsert": "true"}, data=handle, timeout=120,
        )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Textbook upload failed ({response.status_code}).")
    return {"bucket": BUCKET, "object": OBJECT, "sha256": sha256(source), "bytes": source.stat().st_size}


def sync_source_to_cache() -> bool:
    """Download the private canonical PDF atomically; returns False if absent."""
    if not configured():
        return False
    response = requests.get(f"{_URL}/storage/v1/object/{BUCKET}/{OBJECT}", headers=_headers(), timeout=120)
    if response.status_code == 404:
        return False
    if not response.ok:
        raise RuntimeError(f"Textbook download failed ({response.status_code}).")
    PDF_FILE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=PDF_FILE.parent, delete=False) as handle:
        handle.write(response.content)
        temporary = Path(handle.name)
    temporary.replace(PDF_FILE)
    return True
