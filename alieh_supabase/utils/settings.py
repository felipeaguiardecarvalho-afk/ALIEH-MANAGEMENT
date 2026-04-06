from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bootstrap_env() -> None:
    """Carrega variáveis de ``.env`` na raiz do repo (sem sobrescrever o ambiente)."""
    env_path = _repo_root() / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


def get_supabase_config() -> tuple[str, str]:
    bootstrap_env()
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError(
            "Defina SUPABASE_URL e SUPABASE_ANON_KEY (ambiente, .env ou segredos Streamlit)."
        )
    return url, key
