"""
Serviço RAG: extração de intenção → embedding → busca vetorial → inferência LLM (Groq).
Reduz diluição de vetor e evita classificação indevida de processos internos.
"""
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

import httpx
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import (
    EMBEDDING_API_URL,
    EMBEDDING_MODEL,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
)
from app.db.models import IaServicoVetor

TEXTO_MAX_LLM = 6000


def _extrair_intencao(texto_processo: str) -> str | None:
    """
    Etapa 1: Extração de Intenção.
    Chama a LLM (Groq) para obter frase curta com Órgão e Assunto/Pedido principal.
    Remove boilerplate (CPF, endereços, assinaturas) que dilui o vetor.
    """
    if not GROQ_API_KEY or not texto_processo.strip():
        return None
    texto_limitado = texto_processo.strip()[:TEXTO_MAX_LLM]
    system = (
        "Você é um extrator de intenções. Leia este documento e retorne APENAS uma frase curta "
        "dizendo qual é o Órgão e o Assunto/Pedido principal. Ignore nomes, CPFs, endereços e "
        "textos de assinatura eletrônica. Responda em texto puro, sem JSON, sem formatação."
    )
    try:
        client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"DOCUMENTO:\n{texto_limitado}"},
            ],
            temperature=0.1,
            max_tokens=150,
        )
        intencao = (resp.choices[0].message.content or "").strip()
        return intencao if intencao else None
    except Exception:
        return None


def _gerar_embedding(texto: str) -> list[float] | None:
    """Passo A: Gera embedding via API interna (httpx)."""
    if not texto.strip():
        return None
    payload = {"model": EMBEDDING_MODEL, "texts": [texto.strip()]}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(EMBEDDING_API_URL, json=payload)
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
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError):
        return None


def _busca_vetorial_top3(session: Session, embedding: list[float]) -> list[dict[str, Any]]:
    """Passo B: Busca por cosine_distance em ia_servicos_vetores (sem JOIN - banco único). Retorna Top 3."""
    if not embedding:
        return []
    stmt = (
        session.query(IaServicoVetor)
        .where(IaServicoVetor.embedding.isnot(None))
        .order_by(IaServicoVetor.embedding.cosine_distance(embedding))
        .limit(3)
    )
    rows = stmt.all()
    return [
        {
            "nome": r.nome or "",
            "descricao": r.descricao or "",
            "texto_concatenado": r.texto_concatenado or "",
            "id": r.servico_id,
        }
        for r in rows
    ]


def _inferir_com_llm(texto_processo: str, servicos_sugeridos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Etapa 3: Inferência LLM com rota de fuga.
    Retorna JSON com regra: processos internos → id_servico null, servico_identificado 'Processo Interno / Não Mapeado'.
    """
    if not GROQ_API_KEY:
        return None
    servicos_str = "\n".join(
        f"- ID {s['id']}: {s['nome']} | {s['descricao'][:200]}..."
        for s in servicos_sugeridos
    )
    texto_limitado = texto_processo.strip()[:TEXTO_MAX_LLM]
    system_prompt = """Você é um Despachante Público da Prefeitura. Sua função é:
1. Ler o texto do pedido/documento.
2. Analisar as opções de serviços disponíveis (lista abaixo).
3. Identificar o serviço mais adequado ao pedido (se houver).
4. Resumir o pedido em 2 linhas.
5. Listar documentos que possam estar faltando (RG, CPF, comprovante, etc.).
6. Classificar a documentação como COMPLETA ou INCOMPLETA.

IMPORTANTE: Se o documento for um Memorando Interno, RH, ofício interno administrativo, ou se NENHUM dos 3 serviços fornecidos tiver relação óbvia com o pedido, você DEVE retornar o "id_servico" como null e "servico_identificado" como "Processo Interno / Não Mapeado".

Responda OBRIGATORIAMENTE em JSON válido com as chaves: servico_identificado, id_servico, resumo_pedido, documentos_faltantes (array de strings), status_documentacao."""

    user_content = f"""TEXTO DO DOCUMENTO:
{texto_limitado}

OPÇÕES DE SERVIÇOS DISPONÍVEIS (escolha o mais adequado, ou use rota de fuga se for processo interno):
{servicos_str}"""

    client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        conteudo_resposta = resp.choices[0].message.content or ""
        # Sanitização: remove blocos markdown (```json, ```JSON, ```) que a LLM pode inserir
        conteudo_limpo = conteudo_resposta.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
        return json.loads(conteudo_limpo)
    except json.JSONDecodeError as e:
        logger.warning("JSON inválido na resposta da Groq: %s | conteudo=%r", e, conteudo_resposta[:200])
        return None
    except Exception as e:
        logger.error("Erro de API da Groq: %s", e)
        return {
            "servico_identificado": "ERRO DE API - Tente novamente",
            "id_servico": None,
            "resumo_pedido": "",
            "documentos_faltantes": [],
            "status_documentacao": "INCOMPLETA",
        }


def executar_triagem(session: Session, texto_processo: str) -> dict[str, Any]:
    """
    Pipeline RAG: extração de intenção → embedding (vetor limpo) → busca vetorial Top 3 → inferência LLM.
    Reduz diluição de vetor usando intenção extraída em vez do documento integral.
    """
    resultado: dict[str, Any] = {
        "servico_identificado": "",
        "id_servico": None,
        "resumo_pedido": "",
        "documentos_faltantes": [],
        "status_documentacao": "INCOMPLETA",
    }

    # Etapa 1: Extração de Intenção (reduz boilerplate que dilui o vetor)
    intencao_limpa = _extrair_intencao(texto_processo)
    texto_para_embedding = intencao_limpa if intencao_limpa else texto_processo.strip()[:2000]
    if not texto_para_embedding:
        resultado["resumo_pedido"] = "Erro ao extrair intenção do documento."
        return resultado

    # Etapa 2: Busca vetorial com vetor de alta precisão (intenção limpa)
    embedding = _gerar_embedding(texto_para_embedding)
    if not embedding:
        resultado["resumo_pedido"] = "Erro ao gerar embedding. Tente novamente."
        return resultado

    servicos = _busca_vetorial_top3(session, embedding)
    if not servicos:
        resultado["resumo_pedido"] = "Nenhum serviço similar encontrado no catálogo."
        return resultado

    llm_out = _inferir_com_llm(texto_processo, servicos)
    if llm_out:
        resultado["servico_identificado"] = str(llm_out.get("servico_identificado", ""))
        id_raw = llm_out.get("id_servico")
        try:
            resultado["id_servico"] = int(id_raw) if id_raw is not None else None
        except (TypeError, ValueError):
            resultado["id_servico"] = None
        resultado["resumo_pedido"] = str(llm_out.get("resumo_pedido", ""))
        docs = llm_out.get("documentos_faltantes")
        resultado["documentos_faltantes"] = [str(d) for d in docs] if isinstance(docs, list) else []
        resultado["status_documentacao"] = str(llm_out.get("status_documentacao", "INCOMPLETA"))
    else:
        resultado["resumo_pedido"] = "Erro na inferência do LLM. Serviço sugerido (1º do ranking): " + (
            servicos[0]["nome"] if servicos else ""
        )
        resultado["servico_identificado"] = servicos[0]["nome"] if servicos else ""
        resultado["id_servico"] = servicos[0]["id"] if servicos else None

    return resultado
