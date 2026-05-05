from __future__ import annotations

import json
import os
import uuid

import _path  # noqa: F401
from confluence_sync_tool.security import WindowsCredentialStore, credential_key


def main() -> int:
    base_url = "https://credential-smoke.invalid"
    email = f"codex-smoke-{uuid.uuid4().hex}@example.invalid"
    token = f"sentinel-token-{uuid.uuid4().hex}"
    store = WindowsCredentialStore()
    key = credential_key(base_url, email)
    try:
        written_key = store.write(base_url, email, token)
        read_back = store.read(base_url, email)
        store.delete(base_url, email)
        deleted = store.read(base_url, email) is None
        ok = written_key == key and read_back == token and deleted
        print(json.dumps({"ok": ok, "credential_key": key, "read_back_matches": read_back == token, "deleted": deleted}, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        store.delete(base_url, email)


if __name__ == "__main__":
    raise SystemExit(main())
