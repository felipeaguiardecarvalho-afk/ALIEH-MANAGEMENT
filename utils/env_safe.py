"""Exceções comuns ao ler configuração / Streamlit sem mudar a semântica dos fallbacks."""

from __future__ import annotations

# Falhas esperadas ao importar ou aceder a ``st.secrets`` fora do runtime normal.
STREAMLIT_CONFIG_READ_ERRORS: tuple[type[BaseException], ...] = (
    ImportError,
    ModuleNotFoundError,
    AttributeError,
    KeyError,
    RuntimeError,
    TypeError,
    OSError,
)

# Falhas ao resolver caminhos do sistema de ficheiros.
PATH_RESOLVE_ERRORS: tuple[type[BaseException], ...] = (OSError, RuntimeError, ValueError)
