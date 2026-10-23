"""Estado ao vivo da frota sobre SQLite (fase 2 do roadmap).

O loop de simulação grava posição/rumo a cada tick e os endpoints apenas leem
— assim embarcações, ETA, grade de partidas e rastreamento consultam a MESMA
fonte (docs/VISAO_PRODUTO.md §4/§7), substituindo a lista em memória da fase 1.

O seed é idempotente: cria operador demo + embarcações + rota Oriximiná→Óbidos
com partidas e tarifas apenas quando o banco está vazio. As coordenadas dos
portos permanecem as mesmas da fase 1, preservando os testes já existentes.
"""

import persistencia as db
from seguranca import hash_senha, normalizar_email

# Portos de referência (fase 1) — agora também gravados como Rota no banco.
ORIGEM_ORIXIMINA = (-1.7656, -55.8661)
DESTINOS_CONHECIDOS = {
    "Óbidos": (-1.9056, -55.5186),
    "Oriximiná": ORIGEM_ORIXIMINA,
}


def carregar_todas() -> list:
    return db.listar_embarcacoes()


def obter(id_embarcacao: int):
    return db.embarcacao_por_id(id_embarcacao)


def salvar_passo(id_embarcacao: int, latitude: float, longitude: float, rumo: float) -> None:
    db.atualizar_posicao(id_embarcacao, latitude, longitude, rumo)


def semear_banco() -> None:
    """Popula dados de demonstração na primeira execução (nunca duplica)."""
    if db.listar_embarcacoes():
        return

    id_operador = db.inserir_usuario(
        nome="Operador Demo",
        email=normalizar_email("operador@uruat.example"),
        hash_senha=hash_senha("UruaT@2026demo"),
        papel="operador",
    )
    frotas = [
        ("Barco Solimões", "Transporte", 9.5, -1.78, -55.87),
        ("Amazon Star", "Turismo", 6.2, -1.76, -55.85),
    ]
    for nome, tipo, velocidade_no, lat, lon in frotas:
        id_emb = db.inserir_embarcacao(id_operador, nome, tipo, velocidade_no, lat, lon)
        id_rota = db.inserir_rota(
            id_emb, origem="Oriximiná", destino="Óbidos",
            lat_origem=ORIGEM_ORIXIMINA[0], lon_origem=ORIGEM_ORIXIMINA[1],
            lat_destino=DESTINOS_CONHECIDOS["Óbidos"][0],
            lon_destino=DESTINOS_CONHECIDOS["Óbidos"][1],
        )
        # Grade: terças, quintas às 06:00 e sábados às 05:30 (hora local UTC-3).
        for dia, hora in [(1, "06:00"), (3, "06:00"), (5, "05:30")]:
            db.inserir_partida(id_rota, dia_semana=dia, hora=hora)
        db.inserir_tarifa(id_rota, escala="1ª classe", preco_centavos=12000)
        db.inserir_tarifa(id_rota, escala="tombolo", preco_centavos=8000)
