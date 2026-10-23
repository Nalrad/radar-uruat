from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from calculo_eta import calcular_distancia, calcular_eta
from main import app, embarcacoes
from simulacao import mover_todas, passo_simulado


@pytest.fixture
def client():
    # lifespan roda via context manager -> simulação em background ativa
    with TestClient(app) as c:
        yield c


# ── simulacao.py (lógica única extraída da duplicação) ───────
class FakeEmbarcacao:
    def __init__(self, lat, lon):
        self.latitude, self.longitude, self.rumo = lat, lon, 0.0


def test_passo_simulado_move_e_calcula_rumo():
    e = FakeEmbarcacao(0.0, 0.0)
    passo_simulado(e)
    assert (e.latitude, e.longitude) != (0.0, 0.0)
    assert 0 <= e.rumo < 360


def test_mover_todas_aplica_em_todos():
    a, b = FakeEmbarcacao(1.0, 2.0), FakeEmbarcacao(3.0, 4.0)
    mover_todas([a, b])
    for e in (a, b):
        assert abs(e.latitude - round(e.latitude, 6)) < 1  # sanidade
    assert (a.latitude, a.longitude) != (1.0, 2.0)
    assert (b.latitude, b.longitude) != (3.0, 4.0)


# ── Endpoint /embarcacoes ─────────────────────────────────────
def test_listar_embarcacoes_tem_rumo_e_atualizado_em(client):
    resp = client.get("/embarcacoes")
    assert resp.status_code == 200
    dados = resp.json()
    assert len(dados) >= 2
    primeiro = dados[0]
    # Campos novos exigidos pelo frontend (docs §5.2/§5.3)
    assert "rumo" in primeiro
    assert "atualizado_em" in primeiro
    assert 0 <= primeiro["rumo"] < 360


# ── Endpoint /embarcacoes/{id}/eta (integração do cálculo isolado) ──
def test_eta_destino_conhecido(client):
    resp = client.get("/embarcacoes/1/eta", params={"destino": "Óbidos"})
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["destino"] == "Óbidos"
    assert corpo["distancia_km"] > 0
    assert corpo["velocidade_kmh"] == pytest.approx(9.5 * 1.852, rel=0.01)
    assert corpo["eta_tempo_min"] is not None
    assert corpo["hora_chegada_prevista"] is not None
    # coerência interna: tempo = distância / velocidade
    esperado_h = corpo["distancia_km"] / corpo["velocidade_kmh"]
    assert abs(corpo["eta_tempo_min"] / 60 - esperado_h) < 0.05


def test_eta_embarcacao_inexistente(client):
    resp = client.get("/embarcacoes/999/eta", params={"destino": "Óbidos"})
    assert resp.status_code == 404


def test_eta_destino_desconhecido(client):
    resp = client.get("/embarcacoes/1/eta", params={"destino": "Atlântico"})
    assert resp.status_code == 404
    assert "desconhecido" in resp.json()["detail"]


def test_eta_destino_unicode_decomposto(client):
    # Teclados móveis enviam 'O' + acento combinante (NFD); o lookup
    # normaliza para NFC e deve encontrar 'Óbidos'.
    resp = client.get("/embarcacoes/1/eta", params={"destino": "O\u0301bidos"})
    assert resp.status_code == 200
    assert resp.json()["destino"] == "O\u0301bidos"  # ecoa o que o cliente enviou
    assert resp.json()["eta_tempo_min"] is not None


# ── /simular-movimento usa a MESMA função do loop (sem duplicação) ──
def test_simulacao_manual_move_embarcacoes(client):
    antes = [(e.latitude, e.longitude) for e in embarcacoes]
    resp = client.post("/simular-movimento")
    assert resp.status_code == 200
    depois = [(e.latitude, e.longitude) for e in embarcacoes]
    assert antes != depois


# ── conversão nós -> km/h usada no ETA ───────────────────────
def test_velocidade_zero_sem_previsao(client):
    alvo = embarcacoes[0]
    original = alvo.velocidade
    try:
        alvo.velocidade = 0.0
        resp = client.get("/embarcacoes/1/eta", params={"destino": "Óbidos"})
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["eta_tempo_min"] is None
        assert "parada" in corpo["mensagem"]
    finally:
        alvo.velocidade = original
