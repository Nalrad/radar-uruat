"""Fixture de banco isolado p/ suíte da fase 2 (auth, viagem, frota).

Cada teste recebe um SQLite temporário: apontamos a variável URUAT_DB e o
atributo DB_PATH do módulo ANTES de qualquer requisição — nada toca no banco
de desenvolvimento. O lifespan do TestClient inicializa e semeia o banco.
"""

import pytest
from fastapi.testclient import TestClient

import persistencia as db
from main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    arquivobanco = str(tmp_path / "teste.db")
    monkeypatch.setenv("URUAT_DB", arquivobanco)
    monkeypatch.setattr(db, "DB_PATH", arquivobanco)
    with TestClient(app) as c:
        yield c


SENA_FORTE = "UruaT@2026"


def _cadastro(client, nome, email, senha=SENA_FORTE, papel="passageiro"):
    return client.post("/auth/cadastro",
                       json={"nome": nome, "email": email, "senha": senha, "papel": papel})


def _login(client, email, senha=SENA_FORTE):
    resp = client.post("/auth/login", json={"email": email, "senha": senha})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── simulacao.py (lógica única extraída da duplicação) ───────
class FakeEmbarcacao:
    def __init__(self, lat, lon):
        self.latitude, self.longitude, self.rumo = lat, lon, 0.0


def test_passo_simulado_move_e_calcula_rumo():
    from simulacao import passo_simulado
    e = FakeEmbarcacao(0.0, 0.0)
    passo_simulado(e)
    assert (e.latitude, e.longitude) != (0.0, 0.0)
    assert 0 <= e.rumo < 360


def test_passo_simulado_aceita_dict_do_sqlite():
    # Fase 2: o loop opera sobre dicts vindos do banco, não mais Pydantic.
    from simulacao import passo_simulado
    emb = {"latitude": 0.0, "longitude": 0.0, "rumo": 0.0}
    passo_simulado(emb)
    assert emb["latitude"] != 0.0 or emb["longitude"] != 0.0
    assert 0 <= emb["rumo"] < 360


def test_mover_todas_aplica_em_todos():
    from simulacao import mover_todas
    a, b = FakeEmbarcacao(1.0, 2.0), FakeEmbarcacao(3.0, 4.0)
    mover_todas([a, b])
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
    import persistencia as db
    antes = [(e["latitude"], e["longitude"]) for e in db.listar_embarcacoes()]
    resp = client.post("/simular-movimento")
    assert resp.status_code == 200
    depois = [(e["latitude"], e["longitude"]) for e in db.listar_embarcacoes()]
    assert antes != depois


# ── conversão nós -> km/h usada no ETA ───────────────────────
def test_velocidade_zero_sem_previsao(client):
    import persistencia as db
    id_emb = db.listar_embarcacoes()[0]["id_embarcacao"]
    original = db.embarcacao_por_id(id_emb)["velocidade_no"]
    try:
        db._executar("UPDATE Embarcacao SET velocidade_no = 0 WHERE id_embarcacao = ?",
                     (id_emb,))
        resp = client.get(f"/embarcacoes/{id_emb}/eta", params={"destino": "Óbidos"})
        assert resp.status_code == 200
        corpo = resp.json()
        assert corpo["eta_tempo_min"] is None
        assert "parada" in corpo["mensagem"]
    finally:
        db._executar("UPDATE Embarcacao SET velocidade_no = ? WHERE id_embarcacao = ?",
                     (original, id_emb))


# ── Frota vem do banco (fase 2: estado ao vivo em SQLite) ────
def test_seed_idempotente(client):
    import persistencia as db
    from frota import semear_banco
    qtd_antes = len(db.listar_embarcacoes())
    semear_banco()          # segunda execução não deve duplicar
    assert len(db.listar_embarcacoes()) == qtd_antes


def test_posicao_persiste_entre_ticks(client):
    import persistencia as db
    resp1 = client.post("/simular-movimento")
    assert resp1.status_code == 200
    pos1 = [(e["latitude"], e["longitude"], e["rumo"]) for e in db.listar_embarcacoes()]
    resp2 = client.post("/simular-movimento")
    pos2 = [(e["latitude"], e["longitude"], e["rumo"]) for e in db.listar_embarcacoes()]
    assert pos1 != pos2     # o banco guarda o estado entre requisições


# ── Auth: cadastro/login por e-mail com regra de senha (docs §3) ──
def test_cadastro_e_login_ok(client):
    resp = _cadastro(client, "Maria Silva", "maria@exemplo.com.br")
    assert resp.status_code == 201
    cabecalhos = _login(client, "maria@exemplo.com.br")
    perfil = client.get("/auth/eu", headers=cabecalhos)
    assert perfil.status_code == 200
    assert perfil.json()["email"] == "maria@exemplo.com.br"
    assert perfil.json()["papel"] == "passageiro"


def test_cadastro_email_duplicado_retorna_409(client):
    assert _cadastro(client, "A B", "a@x.com").status_code == 201
    assert _cadastro(client, "C D", "a@x.com").status_code == 409


def test_cadastro_senha_fraca_rejeitada(client):
    # <8 chars, sem maiúscula, sem dígito, sem símbolo — todas rejeitadas.
    for senha in ("abc", "abcdefgh", "ABCDEFGH", "abcdefg1"):
        resp = _cadastro(client, "Teste User", f"{senha}@x.com", senha=senha)
        assert resp.status_code == 422, f"senha '{senha}' deveria falhar"


def test_cadastro_email_invalido_rejeitado(client):
    assert _cadastro(client, "Sem Arroba", "nao-e-email").status_code == 422


def test_login_mensagem_nao_revela_email_existente(client):
    _cadastro(client, "Segredo Ok", "segredo@x.com")
    r1 = client.post("/auth/login", json={"email": "segredo@x.com", "senha": "Errada@123"})
    r2 = client.post("/auth/login", json={"email": "ninguem@x.com", "senha": "Errada@123"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]  # anti-enumeração


def test_login_normaliza_caixa_do_email(client):
    _cadastro(client, "Caixa Alta", "joao@x.com")
    resp = client.post("/auth/login", json={"email": "JOAO@X.COM", "senha": SENA_FORTE})
    assert resp.status_code == 200


def test_endpoints_protegidos_exigem_token(client):
    assert client.get("/auth/eu").status_code == 401
    assert client.get("/operador/embarcacoes").status_code == 401
    invalido = {"Authorization": "Bearer n.seca.token"}
    assert client.get("/auth/eu", headers=invalido).status_code == 401


def test_passageiro_nao_gere_frota(client):
    _cadastro(client, "Passageiro P", "p@x.com", papel="passageiro")
    cabecalhos = _login(client, "p@x.com")
    resp = client.post("/operador/embarcacoes",
                       json={"nome": "Barco Clandestino", "latitude": -1.7, "longitude": -55.8},
                       headers=cabecalhos)
    assert resp.status_code == 403


# ── CRUD do operador: embarcação → rota → partida → tarifa ───
def test_fluxo_completo_operador(client):
    _cadastro(client, "Op Teste", "op1@x.com", papel="operador")
    cabecalhos = _login(client, "op1@x.com")

    emb = client.post("/operador/embarcacoes", headers=cabecalhos, json={
        "nome": "Bote Teste", "tipo": "Transporte", "velocidade_no": 7.0,
        "latitude": -1.77, "longitude": -55.86})
    assert emb.status_code == 201
    id_emb = emb.json()["id_embarcacao"]

    rota = client.post(f"/operador/embarcacoes/{id_emb}/rotas", headers=cabecalhos, json={
        "origem": "Oriximiná", "destino": "Santarém",
        "lat_origem": -1.7656, "lon_origem": -55.8661,
        "lat_destino": -2.4431, "lon_destino": -54.7083})
    assert rota.status_code == 201
    id_rota = rota.json()["id_rota"]

    partida = client.post(f"/operador/rotas/{id_rota}/partidas", headers=cabecalhos,
                          json={"dia_semana": 2, "hora": "07:30"})
    assert partida.status_code == 201

    tarifa = client.post(f"/operador/rotas/{id_rota}/tarifas", headers=cabecalhos,
                         json={"escala": "tombolo", "preco_centavos": 9500})
    assert tarifa.status_code == 201

    # A grade nova aparece na consulta pública (sem cadastro — docs §2.1)
    grade = client.get("/rotas").json()
    nossa = next(r for r in grade if r["id_rota"] == id_rota)
    assert nossa["destino"] == "Santarém"
    assert {"dia_semana": 2, "dia_nome": "quarta", "hora": "07:30"} in nossa["partidas"]
    assert {"escala": "tombolo", "preco_centavos": 9500} in nossa["tarifas"]

    # ...e o ETA do operador usa a rota recém-cadastrada no banco
    eta = client.get(f"/embarcacoes/{id_emb}/eta", params={"destino": "Santarém"})
    assert eta.status_code == 200
    assert eta.json()["distancia_km"] > 0


def test_partida_hora_invalida_rejeitada(client):
    _cadastro(client, "Op Hora", "oph@x.com", papel="operador")
    cabecalhos = _login(client, "oph@x.com")
    id_emb = client.post("/operador/embarcacoes", headers=cabecalhos, json={
        "nome": "Barco Hora", "latitude": -1.7, "longitude": -55.8}).json()["id_embarcacao"]
    id_rota = client.post(f"/operador/embarcacoes/{id_emb}/rotas", headers=cabecalhos, json={
        "origem": "Oriximiná", "destino": "Óbidos",
        "lat_origem": -1.76, "lon_origem": -55.86,
        "lat_destino": -1.9, "lon_destino": -55.51}).json()["id_rota"]
    assert client.post(f"/operador/rotas/{id_rota}/partidas", headers=cabecalhos,
                       json={"dia_semana": 2, "hora": "25:00"}).status_code == 422
    assert client.post(f"/operador/rotas/{id_rota}/partidas", headers=cabecalhos,
                       json={"dia_semana": 9, "hora": "07:00"}).status_code == 422


def test_operador_nao_edita_rota_de_outro(client):
    _cadastro(client, "Dono", "dono@x.com", papel="operador")
    _cadastro(client, "Intruso", "intruso@x.com", papel="operador")
    cab_dono = _login(client, "dono@x.com")
    cab_intruso = _login(client, "intruso@x.com")
    id_emb = client.post("/operador/embarcacoes", headers=cab_dono, json={
        "nome": "Barco do Dono", "latitude": -1.7, "longitude": -55.8}).json()["id_embarcacao"]
    id_rota = client.post(f"/operador/embarcacoes/{id_emb}/rotas", headers=cab_dono, json={
        "origem": "Oriximiná", "destino": "Óbidos",
        "lat_origem": -1.76, "lon_origem": -55.86,
        "lat_destino": -1.9, "lon_destino": -55.51}).json()["id_rota"]

    resp = client.post(f"/operador/rotas/{id_rota}/partidas", headers=cab_intruso,
                       json={"dia_semana": 1, "hora": "08:00"})
    assert resp.status_code == 403


# ── Consulta pública de viagem (viagem.py) ───────────────────
def test_rotas_publicas_tem_grade_do_seed(client):
    grade = client.get("/rotas").json()
    assert len(grade) >= 2                      # seed: 1 rota por embarcação
    obidos = next(r for r in grade if r["destino"] == "Óbidos")
    assert len(obidos["partidas"]) == 3         # ter/qui 06:00 + sáb 05:30
    assert {t["preco_centavos"] for t in obidos["tarifas"]} == {12000, 8000}


def test_proxima_partida_calcula_saida_futura(client):
    resp = client.get("/embarcacoes/1/proxima-partida", params={"destino": "Óbidos"})
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["destino"] == "Óbidos"
    assert corpo["saida_hora_local"].endswith("-03:00")   # fuso da operação
    assert corpo["minutos_para_sair"] > 0                 # sempre no futuro


def test_proxima_partida_destino_inexistente(client):
    resp = client.get("/embarcacoes/1/proxima-partida", params={"destino": "Macapá"})
    assert resp.status_code == 404
    assert "Óbidos" in resp.json()["detail"]    # lista opções disponíveis


def test_proxima_partida_unicode_decomposto(client):
    resp = client.get("/embarcacoes/1/proxima-partida", params={"destino": "O\u0301bidos"})
    assert resp.status_code == 200


# ── Unit tests de seguranca.py (regras puras, sem HTTP) ──────
def test_regra_de_senha_docs_secao3():
    from seguranca import senha_valida
    assert senha_valida("UruaT@2026") is True
    assert senha_valida("Ab@1cdef") is True           # exatamente 8 chars: mínimo ok
    assert senha_valida("semSimbolo1A") is False      # falta símbolo
    assert senha_valida("7chr@A1") is False           # 7 caracteres


def test_hash_e_verificacao_de_senha():
    from seguranca import hash_senha, verificar_senha
    h = hash_senha("UruaT@2026")
    assert h != "UruaT@2026" and h.startswith("$2b$")
    assert verificar_senha("UruaT@2026", h) is True
    assert verificar_senha("UruaT@2027", h) is False


def test_token_roundtrip_e_expiracao():
    import time as _t

    import jwt as _jwt
    import pytest as _pytest
    import seguranca
    from seguranca import TokenInvalido, criar_token, decodificar_token
    token = criar_token(42, "a@x.com", "operador")
    claims = decodificar_token(token)
    assert claims["sub"] == "42" and claims["papel"] == "operador"
    assert claims["exp"] > int(_t.time())
    expirado = _jwt.encode({**claims, "exp": int(_t.time()) - 10},
                           seguranca.JWT_SECRET, algorithm="HS256")
    with _pytest.raises(TokenInvalido):
        decodificar_token(expirado)


def test_normalizacao_email_nfc_minusculas():
    import unicodedata
    from seguranca import normalizar_email
    assert normalizar_email("  Joao@X.COM ") == "joao@x.com"
    decomposto = "O\u0301bidos"                       # NFD ('O' + acento combinante)
    esperado = unicodedata.normalize("NFC", decomposto).lower() + "@x.com"
    assert normalizar_email(decomposto.upper() + "@X.COM") == esperado
