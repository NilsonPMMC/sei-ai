"""Rotas RESTful para a Fila de Processos (SEI AI)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import FilaProcesso
from app.db.session import get_db

router = APIRouter()


# --- Pydantic Schemas ---

class ProcessoCreate(BaseModel):
    """Payload para criação/atualização de processo na fila (via RPA)."""
    numero_sei: str = Field(..., max_length=50)
    link_sei: str | None = None
    servico_id: int | None = None
    servico_nome: str | None = None
    resumo_ia: str | None = None
    status_documentacao: str = Field(..., pattern="^(COMPLETA|INCOMPLETA|ERRO)$")
    documentos_faltantes: list[str] = Field(default_factory=list)
    anexos_enviados: list[str] = Field(default_factory=list)


class ProcessoResponse(BaseModel):
    """Resposta ao listar ou criar processo."""
    id: int
    numero_sei: str
    link_sei: str | None
    servico_id: int | None
    servico_nome: str | None
    resumo_ia: str | None
    status_documentacao: str
    documentos_faltantes: list[str]
    anexos_enviados: list[str]
    status_acao: str
    data_criacao: str
    data_atualizacao: str


class ProcessoUpdateAction(BaseModel):
    """Payload para PATCH de ação (aprovar/devolver). Human-in-the-loop: unidade_destino_id."""
    novo_status: str = Field(..., pattern="^(APROVADO|DEVOLVIDO)$")
    unidade_destino_id: int | None = None


# --- Endpoints ---

@router.post("/fila", response_model=ProcessoResponse)
def post_fila(body: ProcessoCreate, db: Session = Depends(get_db)) -> ProcessoResponse:
    """
    Cria ou atualiza processo na fila (UPSERT por numero_sei).
    Chamado pelo RPA com os dados mastigados pela IA.
    """
    stmt = insert(FilaProcesso).values(
        numero_sei=body.numero_sei,
        link_sei=body.link_sei,
        servico_id=body.servico_id,
        servico_nome=body.servico_nome,
        resumo_ia=body.resumo_ia,
        status_documentacao=body.status_documentacao,
        documentos_faltantes=body.documentos_faltantes,
        anexos_enviados=body.anexos_enviados,
        status_acao="PENDENTE",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["numero_sei"],
        set_={
            "link_sei": stmt.excluded.link_sei,
            "servico_id": stmt.excluded.servico_id,
            "servico_nome": stmt.excluded.servico_nome,
            "resumo_ia": stmt.excluded.resumo_ia,
            "status_documentacao": stmt.excluded.status_documentacao,
            "documentos_faltantes": stmt.excluded.documentos_faltantes,
            "anexos_enviados": stmt.excluded.anexos_enviados,
        },
    )
    db.execute(stmt)
    db.commit()
    processo = db.query(FilaProcesso).filter(FilaProcesso.numero_sei == body.numero_sei).one()
    return _to_response(processo)


@router.get("/fila", response_model=list[ProcessoResponse])
def get_fila(db: Session = Depends(get_db)) -> list[ProcessoResponse]:
    """
    Lista processos aguardando atuação do robô ou encaminhamento humano,
    ordenado por data_criacao desc.
    """
    rows = (
        db.query(FilaProcesso)
        .filter(FilaProcesso.status_acao.in_(["PENDENTE", "AGUARDANDO_ROBO"]))
        .order_by(FilaProcesso.data_criacao.desc())
        .all()
    )
    return [_to_response(p) for p in rows]


@router.patch("/fila/acao", response_model=ProcessoResponse)
def patch_fila_acao(
    numero_sei: str,
    body: ProcessoUpdateAction,
    db: Session = Depends(get_db),
) -> ProcessoResponse:
    """
    Atualiza o status_acao do processo (APROVADO ou DEVOLVIDO).
    """
    processo = db.query(FilaProcesso).filter(FilaProcesso.numero_sei == numero_sei).first()
    if not processo:
        raise HTTPException(status_code=404, detail=f"Processo '{numero_sei}' não encontrado.")
    processo.status_acao = body.novo_status
    db.commit()
    db.refresh(processo)
    return _to_response(processo)


def _to_response(p: FilaProcesso) -> ProcessoResponse:
    """Converte FilaProcesso para ProcessoResponse."""
    return ProcessoResponse(
        id=p.id,
        numero_sei=p.numero_sei,
        link_sei=p.link_sei,
        servico_id=p.servico_id,
        servico_nome=p.servico_nome,
        resumo_ia=p.resumo_ia,
        status_documentacao=p.status_documentacao,
        documentos_faltantes=p.documentos_faltantes or [],
        anexos_enviados=p.anexos_enviados or [],
        status_acao=p.status_acao,
        data_criacao=p.data_criacao.isoformat() if p.data_criacao else "",
        data_atualizacao=p.data_atualizacao.isoformat() if p.data_atualizacao else "",
    )
