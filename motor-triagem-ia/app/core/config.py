"""Configurações centralizadas via variáveis de ambiente."""
import os

from dotenv import load_dotenv

load_dotenv()

# Microsserviços: bancos separados
SINAPSE_DB_URL = os.getenv("SINAPSE_DB_URL", "postgresql://postgres:postgres@localhost:5432/sinapse")
SEI_AI_DB_URL = os.getenv("SEI_AI_DB_URL", "postgresql://postgres:postgres@localhost:5432/sei_ai")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "http://192.168.10.50:8004/v1/embeddings")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "mxbai-embed-large")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# API Sinapse (Carta de Serviços) — usada como proxy para evitar CORS no frontend
SINAPSE_API_BASE = os.getenv("SINAPSE_API_BASE", "https://api.mogidascruzes.sp.gov.br/api/v1")
