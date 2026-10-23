"""Lógica de simulação de movimento das embarcações.

Extrai a lógica que antes estava duplicada entre `simular_movimento()`
(loop em background) e o endpoint `/simular-movimento` (disparo manual),
conforme débito técnico listado em docs/VISAO_PRODUTO.md (seção 6).
"""
import math
import random


def passo_simulado(embarcacao, amplitude: float = 0.001) -> None:
    """Aplica um deslocamento aleatório pequeno à embarcação (em graus).

    Também recalcula o rumo (heading, 0-360, 0 = norte) a partir do vetor
    do último deslocamento — usado pelo frontend para orientar o ícone.
    Funciona com objetos Pydantic (fase 1) e com dicts vindos do SQLite
    (fase 2), gravando latitude/longitude/rumo nos dois formatos.
    """
    d_lat = random.uniform(-amplitude, amplitude)
    d_lon = random.uniform(-amplitude, amplitude)
    novo_rumo = (math.degrees(math.atan2(d_lon, d_lat)) + 450) % 360
    if isinstance(embarcacao, dict):
        embarcacao["latitude"] += d_lat
        embarcacao["longitude"] += d_lon
        embarcacao["rumo"] = novo_rumo
    else:
        embarcacao.latitude += d_lat
        embarcacao.longitude += d_lon
        embarcacao.rumo = novo_rumo


def mover_todas(embarcacoes, amplitude: float = 0.001) -> None:
    """Move todas as embarcações da lista (fonte única de verdade)."""
    for embarcacao in embarcacoes:
        passo_simulado(embarcacao, amplitude)
