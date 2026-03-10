"""Endpoint de triagem RAG."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.rag_service import executar_triagem

router = APIRouter()


class ProcessoInput(BaseModel):
    """Payload do endpoint de triagem."""

    texto_processo: str


class TriagemOutput(BaseModel):
    """Resposta estruturada da triagem."""

    servico_identificado: str
    id_servico: int | None
    resumo_pedido: str
    documentos_faltantes: list[str]
    status_documentacao: str


@router.post("/triagem", response_model=TriagemOutput)
def post_triagem(
    body: ProcessoInput,
    db: Session = Depends(get_db),
) -> TriagemOutput:
    """
    Recebe texto do processo, executa RAG (busca vetorial + LLM) e retorna
    o serviço identificado, resumo e status da documentação.
    """
    resultado = executar_triagem(db, body.texto_processo)
    return TriagemOutput(**resultado)
