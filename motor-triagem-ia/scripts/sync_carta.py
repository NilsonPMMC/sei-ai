#!/usr/bin/env python3
"""
Script Smart Sync: Sinapse (catalogo_servico) → embeddings → SEI AI (ia_servicos_vetores).
Sincronização incremental com delta, throttling e UPSERT por lote.
Arquitetura microsserviços: bancos separados.

Uso (a partir da raiz motor-triagem-ia):
    python -m scripts.sync_carta
    python scripts/sync_carta.py
"""
import asyncio
import re
import sys
from pathlib import Path
from typing import Any

# Garante que o pacote app seja encontrado
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import IaServicoVetor, Servico
from app.db.session import SessionAI, SessionSinapse, init_db

EMBEDDING_MOTOR_URL = "http://192.168.10.50:8004/v1/embeddings"
EMBEDDING_TIMEOUT = 30.0
CHUNK_SIZE = 20
SLEEP_ENTRE_LOTES = 2.0


def _strip_html(html: str | None) -> str:
    """Remove tags HTML retornando apenas texto limpo."""
    if not html or not isinstance(html, str):
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip() if text else ""


def _build_texto_concatenado(nome: str, descricao: str) -> str:
    """Concatena nome e descricao para embedding: '{nome}. {descricao}'."""
    n = _strip_html(nome) if nome else ""
    d = _strip_html(descricao) if descricao else ""
    return f"{n}. {d}".strip()


def _fetch_servicos_ativos(session: Session) -> list[dict[str, Any]]:
    """SELECT em catalogo_servico (Sinapse) onde ativo=True. Campos: id, nome, descricao, ativo."""
    stmt = select(Servico.id, Servico.nome, Servico.descricao).where(Servico.ativo == True)
    rows = session.execute(stmt).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        nome = r.nome or ""
        descricao = r.descricao or ""
        texto = _build_texto_concatenado(nome, descricao)
        out.append({
            "servico_id": r.id,
            "nome": _strip_html(nome),
            "descricao": _strip_html(descricao),
            "texto_concatenado": texto,
        })
    return out


def _carregar_existentes_ai(session: Session) -> dict[int, dict[str, Any]]:
    """Carrega ia_servicos_vetores em dicionário: {servico_id: {texto, tem_vetor}}."""
    rows = session.scalars(select(IaServicoVetor)).all()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        texto = (r.texto_concatenado or "").strip()
        tem_vetor = r.embedding is not None
        out[r.servico_id] = {"texto": texto, "tem_vetor": tem_vetor}
    return out


def _montar_fila_processamento(
    servicos: list[dict[str, Any]],
    existentes: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """
    Regra de Fila: entra na fila SE id não existe OU texto mudou OU não tem vetor.
    Retorna (fila_processamento, qtd_ignorados).
    """
    fila: list[dict[str, Any]] = []
    ignorados = 0

    for s in servicos:
        sid = s["servico_id"]
        novo_texto = s["texto_concatenado"].strip()

        if sid not in existentes:
            fila.append(s)
            continue

        ex = existentes[sid]
        texto_salvo = ex["texto"]
        tem_vetor = ex["tem_vetor"]

        if novo_texto != texto_salvo or not tem_vetor:
            fila.append(s)
        else:
            ignorados += 1

    return fila, ignorados


async def _obter_embedding(client: httpx.AsyncClient, texto: str) -> list[float] | None:
    """POST para o motor de embeddings interno."""
    if not texto.strip():
        return None
    payload = {"model": "mxbai-embed-large", "texts": [texto.strip()]}
    try:
        resp = await client.post(
            EMBEDDING_MOTOR_URL,
            json=payload,
            timeout=EMBEDDING_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            emb = data["data"][0].get("embedding")
            if isinstance(emb, list):
                return emb
        if "embeddings" in data and isinstance(data["embeddings"], list) and len(data["embeddings"]) > 0:
            emb = data["embeddings"][0]
            if isinstance(emb, list):
                return emb
        return None
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
        print(f"⚠️ Erro ao obter embedding: {e}")
        if isinstance(e, httpx.HTTPStatusError):
            print(f"   Detalhe do erro {e.response.status_code}: {e.response.text}")
        return None


async def _obter_embeddings_chunk(client: httpx.AsyncClient, textos: list[str]) -> list[list[float] | None]:
    """Obtém embeddings de um chunk em paralelo."""
    if not textos:
        return []
    tasks = [_obter_embedding(client, t) for t in textos]
    return await asyncio.gather(*tasks)


def _upsert_vetores(session: Session, registros: list[dict[str, Any]]) -> int:
    """UPSERT na ia_servicos_vetores (SEI AI). Conflito em servico_id; atualiza campos textuais + embedding."""
    if not registros:
        return 0
    stmt = insert(IaServicoVetor).values(registros)
    stmt = stmt.on_conflict_do_update(
        index_elements=["servico_id"],
        set_={
            "nome": stmt.excluded.nome,
            "descricao": stmt.excluded.descricao,
            "texto_concatenado": stmt.excluded.texto_concatenado,
            "embedding": stmt.excluded.embedding,
        },
    )
    session.execute(stmt)
    session.commit()
    return len(registros)


def _chunks(lst: list[dict[str, Any]], size: int):
    """Divide lista em chunks de até 'size' elementos."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


async def run_sync() -> int:
    """
    Smart Sync: Delta + Throttling + UPSERT incremental.
    a) SessionAI: carrega existentes {servico_id: {texto, tem_vetor}}
    b) SessionSinapse: busca serviços ativos
    c) Monta fila: id novo OU texto mudou OU sem vetor
    d) Processa em lotes de CHUNK_SIZE, sleep entre lotes, UPSERT imediato por lote
    """
    init_db()

    with SessionAI() as session_ai:
        existentes = _carregar_existentes_ai(session_ai)

    with SessionSinapse() as session_sinapse:
        servicos = _fetch_servicos_ativos(session_sinapse)

    if not servicos:
        print("Nenhum serviço ativo em catalogo_servico (Sinapse).")
        return 0

    fila_processamento, ignorados = _montar_fila_processamento(servicos, existentes)
    total_servicos = len(servicos)

    print(f"📊 Smart Sync: {len(servicos)} serviços ativos | {len(fila_processamento)} na fila | {ignorados} ignorados (já atualizados)")

    if not fila_processamento:
        print("Nada a processar. Catálogo já está em dia.")
        return 0

    total_lotes = (len(fila_processamento) + CHUNK_SIZE - 1) // CHUNK_SIZE
    total_upsertados = 0

    async with httpx.AsyncClient() as client:
        for num_lote, chunk in enumerate(_chunks(fila_processamento, CHUNK_SIZE), start=1):
            print(f"⏳ Processando lote {num_lote}/{total_lotes} ({len(chunk)} serviços)...")
            textos = [s["texto_concatenado"] for s in chunk]
            embeddings = await _obter_embeddings_chunk(client, textos)
            falhas = sum(1 for e in embeddings if e is None)
            if falhas > 0:
                print(f"   ⚠️ {falhas} embedding(s) falharam neste lote (timeout/indisponibilidade).")

            registros = [
                {
                    "servico_id": s["servico_id"],
                    "nome": s["nome"],
                    "descricao": s["descricao"],
                    "texto_concatenado": s["texto_concatenado"],
                    "embedding": emb,
                }
                for s, emb in zip(chunk, embeddings)
            ]

            with SessionAI() as session_ai:
                n = _upsert_vetores(session_ai, registros)
            total_upsertados += n

            if num_lote < total_lotes:
                print(f"   ✓ {n} registros salvos. Aguardando {SLEEP_ENTRE_LOTES}s (throttling)...")
                await asyncio.sleep(SLEEP_ENTRE_LOTES)
            else:
                print(f"   ✓ {n} registros salvos.")

    print(f"✅ Sincronização concluída: {total_upsertados} registros inseridos/atualizados em ia_servicos_vetores (SEI AI).")
    return total_upsertados


def main() -> None:
    asyncio.run(run_sync())


if __name__ == "__main__":
    main()
