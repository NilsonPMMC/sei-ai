"""
Proxy para API Sinapse — evita CORS ao fazer as requisições pelo backend.
GET /v1/sinapse/unidades e GET /v1/sinapse/servicos repassam para a API externa.
"""
from fastapi import APIRouter, HTTPException
import httpx

from app.core.config import SINAPSE_API_BASE

router = APIRouter()


@router.get("/sinapse/unidades")
async def get_unidades():
    """
    Repassa GET para a API Sinapse /unidades/.
    Usado pelo frontend para evitar CORS.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(f"{SINAPSE_API_BASE}/unidades/")
            res.raise_for_status()
            return res.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar Sinapse: {str(e)}")


@router.get("/sinapse/servicos")
async def get_servicos():
    """
    Repassa GET para a API Sinapse /servicos/.
    Usado pelo frontend para evitar CORS.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(f"{SINAPSE_API_BASE}/servicos/")
            res.raise_for_status()
            return res.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Falha ao consultar Sinapse: {str(e)}")
