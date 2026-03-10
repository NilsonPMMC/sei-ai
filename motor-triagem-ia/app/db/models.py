"""
Modelos SQLAlchemy para microsserviços (bancos separados).
- BaseSinapse: catalogo_servico (fonte - Sinapse)
- BaseAI: ia_servicos_vetores, fila_processos (SEI AI)
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

BaseSinapse = declarative_base()
BaseAI = declarative_base()

EMBEDDING_DIM = 1024


# --- Banco Sinapse (origem) ---

class Servico(BaseSinapse):
    """
    Modelo mapeado para catalogo_servico no banco Sinapse.
    Fonte da verdade textual (somente leitura pelo ETL).
    """
    __tablename__ = "catalogo_servico"

    id = Column(Integer, primary_key=True)
    nome = Column(String(500), nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Servico(id={self.id}, nome='{self.nome[:30]}...')>"


# --- Banco SEI AI ---

class IaServicoVetor(BaseAI):
    """
    Modelo mapeado para ia_servicos_vetores no banco SEI AI.
    Réplica textual + embedding para RAG (sem JOIN entre bancos).
    Colunas textuais permitem montar o prompt localmente.
    """
    __tablename__ = "ia_servicos_vetores"

    servico_id = Column(Integer, primary_key=True)
    nome = Column(String(500), nullable=True)
    descricao = Column(Text, nullable=True)
    texto_concatenado = Column(Text, nullable=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)

    def __repr__(self) -> str:
        return f"<IaServicoVetor(servico_id={self.servico_id})>"


class FilaProcesso(BaseAI):
    """
    Fila de processos para triagem (SEI AI).
    """
    __tablename__ = "fila_processos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    numero_sei = Column(String(50), unique=True, index=True, nullable=False)
    link_sei = Column(String(500), nullable=True)
    servico_id = Column(Integer, nullable=True)
    servico_nome = Column(String(255), nullable=True)
    resumo_ia = Column(Text, nullable=True)
    status_documentacao = Column(String(50), nullable=False)
    documentos_faltantes = Column(JSONB, default=list, nullable=False)
    anexos_enviados = Column(JSONB, default=list, nullable=False)
    status_acao = Column(String(50), default="PENDENTE", nullable=False)
    data_criacao = Column(DateTime, default=datetime.utcnow, nullable=False)
    data_atualizacao = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<FilaProcesso(numero_sei='{self.numero_sei}', status_acao='{self.status_acao}')>"


# Alias para compatibilidade (legado usa Base)
Base = BaseAI
