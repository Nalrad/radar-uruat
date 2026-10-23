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

import persistencia as db
from auth import router as auth_router
from calculo_eta import calcular_distancia, calcular_eta
from frota import DESTINOS_CONHECIDOS, obter, salvar_passo, semear_banco
from simulacao import mover_todas
from viagem import router as viagem_router

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


def _nfc(s: str) -> str:
    """Normaliza unicode (NFC): 'O'+acentocombinante == 'Ó'.

    Datas de teclado/móveis diferentes podem enviar acentos decompostos;
    sem isso o lookup do destino falharia silenciosamente com 404.
    """
    return unicodedata.normalize("NFC", s)


def _de_dict(emb: dict, agora: datetime) -> Embarcacao:
    """Adaptador SQLite → modelo público (mantém contrato da fase 1)."""
    return Embarcacao(
        id=emb["id_embarcacao"], nome=emb["nome"], tipo=emb["tipo"] or "",
        velocidade=emb["velocidade_no"] or 0.0, bandeira="Brasil",
        latitude=emb["latitude"], longitude=emb["longitude"],
        rumo=emb.get("rumo") or 0.0, atualizado_em=agora,
    )


# ── Ciclo de vida (substitui @app.on_event("startup") deprecado) ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.inicializar_banco()   # fase 2: tabelas Usuario/Embarcacao/Rota/Partida/Tarifa
    semear_banco()           # seed idempotente (operador demo + frota + grade)
    tarefa = asyncio.create_task(simular_movimento())
    yield
    tarefa.cancel()


app = FastAPI(
    title="URUÁ-T API",
    description="Monitoramento de embarcações fluviais — Oriximiná/PA",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS restrito por variável de ambiente (docs §5.6); em dev libera localhost.
_origens = os.environ.get("CORS_ORIGENS", "").split(",") if os.environ.get("CORS_ORIGENS") else [
    "http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:8000", "http://localhost:8000",
]
app.add_middleware(CORSMiddleware, allow_origins=_origens, allow_methods=["*"], allow_headers=["*"])

# Fase 2: autenticação/cadastro (auth.py) e consultas públicas de viagem (viagem.py)
app.include_router(auth_router)
app.include_router(viagem_router)


# ── Simulação de movimento (lógica única em simulacao.py) ────
async def simular_movimento():
    while True:
        passo_de_simulacao()
        await asyncio.sleep(INTERVALO_ATUALIZACAO)


def passo_de_simulacao() -> datetime:
    """Um tick: move a frota (dicts do SQLite) e persiste posição/rumo.

    Compartilhado pelo loop em background e pelo endpoint manual — a mesma
    função é a fonte de verdade (débito técnico quitado na fase 1).
    """
    embarcacoes = db.listar_embarcacoes()
    mover_todas(embarcacoes)
    agora = datetime.now(timezone.utc)
    for emb in embarcacoes:
        salvar_passo(emb["id_embarcacao"], emb["latitude"], emb["longitude"], emb["rumo"])
    return agora


# ── Endpoints ─────────────────────────────────────────────────
@app.get("/embarcacoes", response_model=List[Embarcacao])
def listar_embarcacoes():
    agora = datetime.now(timezone.utc)
    return [_de_dict(e, agora) for e in db.listar_embarcacoes()]


@app.post("/simular-movimento")
def simular_movimento_manual():
    """Disparo manual de um passo da simulação (mesma função do loop)."""
    passo_de_simulacao()
    return {"status": "Movimento simulado manualmente"}


@app.get("/embarcacoes/{embarcacao_id}/eta", response_model=EtaResposta)
def consultar_eta(
    embarcacao_id: int,
    destino: str = Query(..., description="Nome do destino (ex.: 'Óbidos')"),
):
    """ETA em tempo real: distância Haversine × velocidade desenvolvida.

    Fase 2: as coordenadas do destino vêm da tabela Rota cadastrada pelo
    operador; se a rota ainda não existe no banco, caímos nos portos fixos
    da fase 1 (DESTINOS_CONHECIDOS) para não quebrar clientes antigos.
    """
    emb = obter(embarcacao_id)
    if emb is None:
        raise HTTPException(status_code=404, detail="Embarcação não encontrada")

    rota = db.rota_por_destino(embarcacao_id, _nfc(destino))
    if rota is not None:
        coords = (rota["lat_destino"], rota["lon_destino"])
    else:
        coords = DESTINOS_CONHECIDOS.get(_nfc(destino))
    if coords is None:
        disponiveis = [r["destino"] for r in db.rotas_da_embarcacao(embarcacao_id)] \
            or list(DESTINOS_CONHECIDOS)
        raise HTTPException(
            status_code=404,
            detail=f"Destino '{destino}' desconhecido. Disponíveis: {', '.join(disponiveis)}",
        )

    distancia = calcular_distancia(emb["latitude"], emb["longitude"], coords[0], coords[1])
    velocidade_kmh = (emb["velocidade_no"] or 0.0) * 1.852  # nós -> km/h
    eta = calcular_eta(distancia, velocidade_kmh)

    if eta is None:
        return EtaResposta(
            embarcacao_id=emb["id_embarcacao"], embarcacao_nome=emb["nome"], destino=destino,
            distancia_km=round(distancia, 2), velocidade_kmh=round(velocidade_kmh, 2),
            eta_tempo_min=None, hora_chegada_prevista=None,
            mensagem="Embarcação parada — sem previsão de chegada",
        )

    agora = datetime.now(timezone.utc)
    return EtaResposta(
        embarcacao_id=emb["id_embarcacao"], embarcacao_nome=emb["nome"], destino=destino,
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
