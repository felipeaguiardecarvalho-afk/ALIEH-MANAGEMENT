"""
Camada de persistência: SQLite na raiz do projeto.

- **Streamlit Community Cloud (live):** sempre `business.db` (detecção automática).
- **Outro servidor de produção:** `ALIEH_PRODUCTION=true` → `business.db`.
- **Dev local:** por defeito `businessdev.db`, ou `sqlite_filename` / `ALIEH_SQLITE`.

- `init_db` em `database.init_db`: cria/migra o schema.
- Módulos `db_*.py`: mapa tabelas ↔ páginas Streamlit.
"""

from database.connection import BASE_DIR, DB_PATH, get_conn
from database.init_db import init_db

__all__ = ["BASE_DIR", "DB_PATH", "get_conn", "init_db"]
