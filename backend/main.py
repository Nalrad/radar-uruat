from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional
import asyncio
import os
import unicodedata

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from calculo_eta import calcular_distancia, calcular_eta
from simulacao import mover_todas

# Intervalo de atualização da simulação (segundos) — espelha CONFIG.UPDATE_SEC
# do frontend; fonte única de verdade no backend.
INTERVALO_ATUALIZACAO = 5


# ── Modelos de dados ─────────────────────────────────────────
class Embarcacao(BaseModel):
    id: int
    nome: str
    tipo: str
    velocidade: float          # nós (padrão náutico)
    bandeira: str
    latitude: float
    longitude: float
    rumo: float = 0.0          # heading 0-360, 0 = norte
    atualizado_em: Optional[datetime] = None  # idade do último sinal (docs §5.3)


class EtaResposta(BaseModel):
    embarcacao_id: int
    embarcacao_nome: str
    destino: str
    distancia_km: float
    velocidade_kmh: float
    eta_tempo_min: Optional[float]  # None = não chegará (velocidade 0)
    hora_chegada_prevista: Optional[datetime]
    mensagem: Optional[str] = None


# Destinos conhecidos para o ETA enquanto a tabela Rota não existe
# (ver docs/VISAO_PRODUTO.md §4). Depois virá do banco via operador.
def _nfc(s: str) -> str:
    """Normaliza unicode (NFC): 'O'+acentocombinante == 'Ó'.

    Datas de teclado/móveis diferentes podem enviar acentos decompostos;
    sem isso o lookup do destino falharia silenciosamente com 404.
    """
    return unicodedata.normalize("NFC", s)


DESTINOS_CONHECIDOS = {
    _nfc("Óbidos"): (-1.9056, -55.5186),
    _nfc("Oriximiná"): (-1.7656, -55.8661),
}

# Lista inicial de embarcações
embarcacoes: List[Embarcacao] = [
    Embarcacao(id=1, nome="Barco Solimões", tipo="Transporte", velocidade=9.5,
               bandeira="Brasil", latitude=-1.78, longitude=-55.87),
    Embarcacao(id=2, nome="Amazon Star", tipo="Turismo", velocidade=6.2,
               bandeira="Brasil", latitude=-1.76, longitude=-55.85),
]


# ── Ciclo de vida (substitui @app.on_event("startup") deprecado) ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    tarefa = asyncio.create_task(simular_movimento())
    yield
    tarefa.cancel()


app = FastAPI(
    title="URUÁ-T API",
    description="Monitoramento de embarcações fluviais — Oriximiná/PA",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS restrito por variável de ambiente (docs §5.6); em dev libera localhost.
_origens = os.environ.get("CORS_ORIGENS", "").split(",") if os.environ.get("CORS_ORIGENS") else [
    "http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:8000", "http://localhost:8000",
]
app.add_middleware(CORSMiddleware, allow_origins=_origens, allow_methods=["GET", "POST"], allow_headers=["*"])


# ── Simulação de movimento (lógica única em simulacao.py) ────
async def simular_movimento():
    while True:
        mover_todas(embarcacoes)
        agora = datetime.now(timezone.utc)
        for embarcacao in embarcacoes:
            embarcacao.atualizado_em = agora
        await asyncio.sleep(INTERVALO_ATUALIZACAO)


# ── Endpoints ─────────────────────────────────────────────────
@app.get("/embarcacoes", response_model=List[Embarcacao])
def listar_embarcacoes():
    return embarcacoes


@app.post("/simular-movimento")
def simular_movimento_manual():
    """Disparo manual de um passo da simulação (mesma função do loop)."""
    mover_todas(embarcacoes)
    agora = datetime.now(timezone.utc)
    for embarcacao in embarcacoes:
        embarcacao.atualizado_em = agora
    return {"status": "Movimento simulado manualmente"}


@app.get("/embarcacoes/{embarcacao_id}/eta", response_model=EtaResposta)
def consultar_eta(
    embarcacao_id: int,
    destino: str = Query(..., description="Nome do destino (ex.: 'Óbidos')"),
):
    """ETA em tempo real: distância Haversine × velocidade desenvolvida."""
    emb = next((e for e in embarcacoes if e.id == embarcacao_id), None)
    if emb is None:
        raise HTTPException(status_code=404, detail="Embarcação não encontrada")

    coords = DESTINOS_CONHECIDOS.get(_nfc(destino))
    if coords is None:
        raise HTTPException(
            status_code=404,
            detail=f"Destino '{destino}' desconhecido. Disponíveis: {', '.join(DESTINOS_CONHECIDOS)}",
        )

    distancia = calcular_distancia(emb.latitude, emb.longitude, coords[0], coords[1])
    velocidade_kmh = emb.velocidade * 1.852  # nós -> km/h
    eta = calcular_eta(distancia, velocidade_kmh)

    if eta is None:
        return EtaResposta(
            embarcacao_id=emb.id, embarcacao_nome=emb.nome, destino=destino,
            distancia_km=round(distancia, 2), velocidade_kmh=round(velocidade_kmh, 2),
            eta_tempo_min=None, hora_chegada_prevista=None,
            mensagem="Embarcação parada — sem previsão de chegada",
        )

    agora = datetime.now(timezone.utc)
    return EtaResposta(
        embarcacao_id=emb.id, embarcacao_nome=emb.nome, destino=destino,
        distancia_km=round(distancia, 2), velocidade_kmh=round(velocidade_kmh, 2),
        eta_tempo_min=eta.total_seconds() / 60,
        hora_chegada_prevista=agora + eta,
    )


# ── Frontend ──────────────────────────────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "static")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
