"""Endpoints públicos de viagem — fase 2, linha 2 do roadmap (docs §7).

O passageiro NÃO precisa de cadastro para consultar (docs §2.1): estes
endpoints são abertos e respondem à "pergunta única": esta embarcação faz
este trecho? quando parte? quanto custa? quando chega?

- GET /rotas                       grade completa (rota + partidas + tarifas)
- GET /embarcacoes/{id}/proxima-partida?destino=...   próxima saída calculada
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
import unicodedata

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import persistencia as db

router = APIRouter(tags=["viagem"])

# Fuso de referência da operação ribeirinha (Oriximiná/Óbidos, PA): UTC-3.
# Sem dependência de zoneinfo no deploy; ajustar se a frota cruzar fusos.
FUSO_OPERACAO = timezone(timedelta(hours=-3))

DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


class TarifaPublica(BaseModel):
    escala: Optional[str]
    preco_centavos: int


class PartidaPublica(BaseModel):
    dia_semana: int          # 0=segunda
    dia_nome: str
    hora: str                # 'HH:MM' local


class RotaPublica(BaseModel):
    id_rota: int
    id_embarcacao: int
    embarcacao_nome: str
    origem: str
    destino: str
    partidas: List[PartidaPublica]
    tarifas: List[TarifaPublica]


class ProximaPartida(BaseModel):
    embarcacao_id: int
    embarcacao_nome: str
    destino: str
    saida_hora_local: str            # ISO com offset
    minutos_para_sair: int
    em_partida: bool                 # embarcação já está navegando p/ o destino
    distancias_km_eta: Optional[float] = None
    eta_minutos: Optional[float] = None


@router.get("/rotas", response_model=List[RotaPublica])
def listar_rotas():
    """Grade comercial completa, pública por definição (sem cadastro)."""
    resultado: List[RotaPublica] = []
    embarcacoes = {e["id_embarcacao"]: e for e in db.listar_embarcacoes()}
    for rota in db.todas_rotas():
        emb = embarcacoes.get(rota["id_embarcacao"])
        if emb is None:
            continue
        partidas = [
            PartidaPublica(dia_semana=p["dia_semana"],
                           dia_nome=DIAS_SEMANA[p["dia_semana"]],
                           hora=p["hora"])
            for p in db.partidas_da_rota(rota["id_rota"])
        ]
        tarifas = [TarifaPublica(**t) for t in db.tarifas_da_rota(rota["id_rota"])]
        resultado.append(RotaPublica(
            id_rota=rota["id_rota"], id_embarcacao=emb["id_embarcacao"],
            embarcacao_nome=emb["nome"], origem=rota["origem"], destino=rota["destino"],
            partidas=partidas, tarifas=tarifas,
        ))
    return resultado


def _parse_hora(hhmm: str) -> Tuple[int, int]:
    h, m = hhmm.split(":")
    return int(h), int(m)


def _proxima_saida_local(dia_semana: int, hora: str, agora_local: datetime) -> datetime:
    """Próxima ocorrência de 'dia HH:MM' estritamente após `agora_local`."""
    h, m = _parse_hora(hora)
    dias_ate = (dia_semana - agora_local.weekday()) % 7
    candidata = agora_local.replace(hour=h, minute=m, second=0, microsecond=0) \
        + timedelta(days=dias_ate)
    if candidata <= agora_local:
        candidata += timedelta(days=7)
    return candidata


@router.get("/embarcacoes/{embarcacao_id}/proxima-partida", response_model=ProximaPartida)
def proxima_partida(
    embarcacao_id: int,
    destino: str = Query(..., description="Nome do destino (ex.: 'Óbidos')"),
):
    """Combina grade (Partida) com estado ao vivo (posição/velocidade).

    Status 'em_partida': se a embarcação já deixou o porto de origem em
    direção ao destino (velocidade > 0 e rota cadastrada), informamos também
    o ETA em tempo real — é a resposta mais honesta que um app de tracking
    pode dar (benchmark: MarineTraffic/Boating, docs §5).
    """
    emb = db.embarcacao_por_id(embarcacao_id)
    if emb is None:
        raise HTTPException(404, "Embarcação não encontrada")

    destino_nfc = _nfc(destino)
    rota = db.rota_por_destino(embarcacao_id, destino_nfc)
    if rota is None:
        disponiveis = [r["destino"] for r in db.rotas_da_embarcacao(embarcacao_id)]
        raise HTTPException(
            404,
            f"Destino '{destino}' não opera nesta embarcação."
            + (f" Disponíveis: {', '.join(disponiveis)}" if disponiveis else ""),
        )

    partidas = db.partidas_da_rota(rota["id_rota"])
    agora_local = datetime.now(FUSO_OPERACAO)

    if partidas:
        proxima = min(
            (_proxima_saida_local(p["dia_semana"], p["hora"], agora_local), p)
            for p in partidas
        )[0]
    else:
        # Rota sem grade cadastrada ainda não é uma viagem vendável; mas se a
        # embarcação estiver navegando, o passageiro merece ver o ETA (docs §5.2).
        proxima = None

    # Estado de navegação: distância atual vs. distância total do trecho.
    from calculo_eta import calcular_distancia, calcular_eta
    dist_atual = calcular_distancia(emb["latitude"], emb["longitude"],
                                    rota["lat_destino"], rota["lon_destino"])
    dist_trecho = calcular_distancia(rota["lat_origem"], rota["lon_origem"],
                                     rota["lat_destino"], rota["lon_destino"])
    navegando = bool(emb["velocidade_no"]) and emb["velocidade_no"] > 0.5 \
        and dist_atual < dist_trecho * 0.95

    eta_min = None
    if navegando:
        eta_seg = calcular_eta(dist_atual, emb["velocidade_no"] * 1.852)
        eta_min = round(eta_seg.total_seconds() / 60, 1) if eta_seg else None

    saida_iso = proxima.isoformat(timespec="minutes") if proxima else None
    mins_para = max(0, round((proxima - agora_local).total_seconds() / 60)) if proxima else None

    return ProximaPartida(
        embarcacao_id=emb["id_embarcacao"],
        embarcacao_nome=emb["nome"],
        destino=rota["destino"],
        saida_hora_local=saida_iso or "",
        minutos_para_sair=mins_para if mins_para is not None else -1,
        em_partida=bool(navegando),
        distancias_km_eta=round(dist_atual, 2) if navegando else None,
        eta_minutos=eta_min,
    )
