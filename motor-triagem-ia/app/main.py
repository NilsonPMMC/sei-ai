"""FastAPI - Motor de Triagem IA / SEI AI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import fila, sinapse, triagem
from app.db.session import init_db

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        logger.warning("init_db falhou (banco indisponível? pg_hba.conf?): %s", e)
        logger.warning("A API iniciará, mas endpoints que usam o banco falharão até a conexão ser corrigida.")
    yield


app = FastAPI(
    title="Motor de Triagem IA",
    description="RAG + Groq para roteamento inteligente de processos",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Em produção, coloque o domínio real
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(triagem.router, prefix="/v1", tags=["triagem"])
app.include_router(fila.router, prefix="/v1", tags=["fila"])
app.include_router(sinapse.router, prefix="/v1", tags=["sinapse"])
