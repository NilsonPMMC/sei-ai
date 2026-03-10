"""
Configuração de conexão com PostgreSQL (microsserviços - bancos separados).
- SINAPSE_DB_URL: origem dos dados (catalogo_servico)
- SEI_AI_DB_URL: banco de IA (ia_servicos_vetores, fila_processos)
"""
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import SEI_AI_DB_URL, SINAPSE_DB_URL
from app.db.models import BaseAI

engine_sinapse = create_engine(
    SINAPSE_DB_URL,
    pool_pre_ping=True,
    echo=False,
)

engine_ai = create_engine(
    SEI_AI_DB_URL,
    pool_pre_ping=True,
    echo=False,
)

SessionSinapse = sessionmaker(autocommit=False, autoflush=False, bind=engine_sinapse)
SessionAI = sessionmaker(autocommit=False, autoflush=False, bind=engine_ai)


def get_db() -> Generator[Session, None, None]:
    """Generator para injeção de dependência no FastAPI. Retorna SessionAI."""
    db = SessionAI()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Cria tabelas no banco SEI AI e aplica migrações pendentes."""
    with engine_ai.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    BaseAI.metadata.create_all(bind=engine_ai)
    # Migração: adiciona coluna anexos_enviados se não existir
    with engine_ai.connect() as conn:
        conn.execute(text(
            "ALTER TABLE fila_processos ADD COLUMN IF NOT EXISTS anexos_enviados JSONB DEFAULT '[]' NOT NULL"
        ))
        conn.commit()
