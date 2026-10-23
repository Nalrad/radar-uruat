"""Camada de persistência do URUÁ-T — fase 2 do roadmap (docs §6/§7).

O produto mira PostgreSQL em produção, mas o deploy atual não tem banco;
esta camada usa SQLite com a MESMA estrutura lógica de database/schema.sql,
acrescentando as tabelas que faltavam para a grade comercial: Rota (trecho de
navegação), Partida (dias/horários) e Tarifa (preços por escala). A migração
para Postgres vira troca de driver + SERIAL→IDENTITY.

Decisões:
- Conexão curta por operação + lock de escrita: o loop de simulação (5 s) e as
  requisições HTTP compartilham o banco sem corrupção.
- `email` é armazenado normalizado (NFC + minúsculas, ver seguranca.py);
  `destino` de Rota/Tarifa em centavos evitam float de dinheiro.
"""

import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get(
    "URUAT_DB",
    os.path.join(os.path.dirname(__file__), "urua_t.db"),
)

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS Usuario (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,          -- sempre normalizado (NFC + minúsculas)
    hash_senha TEXT NOT NULL,            -- bcrypt; nunca texto puro
    papel TEXT NOT NULL CHECK (papel IN ('passageiro', 'operador'))
);

CREATE TABLE IF NOT EXISTS Embarcacao (
    id_embarcacao INTEGER PRIMARY KEY AUTOINCREMENT,
    id_operador INTEGER REFERENCES Usuario(id_usuario),
    nome TEXT NOT NULL,
    tipo TEXT,
    velocidade_no REAL DEFAULT 0,        -- velocidade desenvolvida (nós)
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    rumo REAL DEFAULT 0
);

-- Trecho de navegação: origem → destino com coordenadas dos dois portos
-- (substitui o dicionário fixo DESTINOS_CONHECIDOS da fase 1).
CREATE TABLE IF NOT EXISTS Rota (
    id_rota INTEGER PRIMARY KEY AUTOINCREMENT,
    id_embarcacao INTEGER NOT NULL REFERENCES Embarcacao(id_embarcacao),
    origem TEXT NOT NULL,
    destino TEXT NOT NULL,               -- normalizado NFC na gravação
    lat_origem REAL NOT NULL,
    lon_origem REAL NOT NULL,
    lat_destino REAL NOT NULL,
    lon_destino REAL NOT NULL
);

-- Grade de partidas: dia da semana + horário local 'HH:MM'.
CREATE TABLE IF NOT EXISTS Partida (
    id_partida INTEGER PRIMARY KEY AUTOINCREMENT,
    id_rota INTEGER NOT NULL REFERENCES Rota(id_rota),
    dia_semana INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),  -- 0=segunda
    hora TEXT NOT NULL CHECK (hora GLOB '[0-2][0-9]:[0-5][0-9]')
);

-- Tarifa por rota e escala (ex.: '1ª classe', 'tombolo'); NULL = preço único.
-- Dinheiro em CENTAVOS (inteiro) — nunca float.
CREATE TABLE IF NOT EXISTS Tarifa (
    id_tarifa INTEGER PRIMARY KEY AUTOINCREMENT,
    id_rota INTEGER NOT NULL REFERENCES Rota(id_rota),
    escala TEXT,
    preco_centavos INTEGER NOT NULL CHECK (preco_centavos >= 0)
);
"""


def conectar() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar_banco() -> None:
    with _lock:
        conn = conectar()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with _lock:
        conn = conectar()
        try:
            return [dict(r) for r in conn.execute(sql, params)]
        finally:
            conn.close()


def _query1(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _query(sql, params)
    return rows[0] if rows else None


def _executar(sql: str, params: tuple = ()) -> int:
    with _lock:
        conn = conectar()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


# ── Usuários ──────────────────────────────────────────────────
def inserir_usuario(nome: str, email: str, hash_senha: str, papel: str) -> int:
    return _executar(
        "INSERT INTO Usuario (nome, email, hash_senha, papel) VALUES (?, ?, ?, ?)",
        (nome, email, hash_senha, papel),
    )


def usuario_por_email(email: str) -> Optional[Dict[str, Any]]:
    return _query1("SELECT * FROM Usuario WHERE email = ?", (email,))


def usuario_por_id(id_usuario: int) -> Optional[Dict[str, Any]]:
    return _query1("SELECT * FROM Usuario WHERE id_usuario = ?", (id_usuario,))


# ── Embarcações ───────────────────────────────────────────────
def inserir_embarcacao(id_operador: int, nome: str, tipo: str, velocidade_no: float,
                       latitude: float, longitude: float) -> int:
    return _executar(
        "INSERT INTO Embarcacao (id_operador, nome, tipo, velocidade_no,"
        " latitude, longitude, rumo) VALUES (?, ?, ?, ?, ?, ?, 0)",
        (id_operador, nome, tipo, velocidade_no, latitude, longitude),
    )


def listar_embarcacoes() -> List[Dict[str, Any]]:
    return _query("SELECT * FROM Embarcacao ORDER BY id_embarcacao")


def embarcacao_por_id(id_embarcacao: int) -> Optional[Dict[str, Any]]:
    return _query1("SELECT * FROM Embarcacao WHERE id_embarcacao = ?", (id_embarcacao,))


def atualizar_posicao(id_embarcacao: int, latitude: float, longitude: float, rumo: float) -> None:
    _executar(
        "UPDATE Embarcacao SET latitude = ?, longitude = ?, rumo = ? WHERE id_embarcacao = ?",
        (latitude, longitude, rumo, id_embarcacao),
    )


# ── Rotas / partidas / tarifas ────────────────────────────────
def inserir_rota(id_embarcacao: int, origem: str, destino: str,
                 lat_origem: float, lon_origem: float,
                 lat_destino: float, lon_destino: float) -> int:
    return _executar(
        "INSERT INTO Rota (id_embarcacao, origem, destino, lat_origem, lon_origem,"
        " lat_destino, lon_destino) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (id_embarcacao, origem, destino, lat_origem, lon_origem, lat_destino, lon_destino),
    )


def rotas_da_embarcacao(id_embarcacao: int) -> List[Dict[str, Any]]:
    return _query("SELECT * FROM Rota WHERE id_embarcacao = ? ORDER BY id_rota", (id_embarcacao,))


def rota_por_destino(id_embarcacao: int, destino: str) -> Optional[Dict[str, Any]]:
    """Lookup do destino do ETA — comparação já normalizada (NFC) nas duas pontas."""
    return _query1(
        "SELECT * FROM Rota WHERE id_embarcacao = ? AND destino = ?",
        (id_embarcacao, destino),
    )


def todas_rotas() -> List[Dict[str, Any]]:
    return _query("SELECT * FROM Rota ORDER BY id_rota")


def inserir_partida(id_rota: int, dia_semana: int, hora: str) -> int:
    return _executar(
        "INSERT INTO Partida (id_rota, dia_semana, hora) VALUES (?, ?, ?)",
        (id_rota, dia_semana, hora),
    )


def partidas_da_rota(id_rota: int) -> List[Dict[str, Any]]:
    return _query(
        "SELECT dia_semana, hora FROM Partida WHERE id_rota = ? ORDER BY dia_semana, hora",
        (id_rota,),
    )


def inserir_tarifa(id_rota: int, escala: Optional[str], preco_centavos: int) -> int:
    return _executar(
        "INSERT INTO Tarifa (id_rota, escala, preco_centavos) VALUES (?, ?, ?)",
        (id_rota, escala, preco_centavos),
    )


def tarifas_da_rota(id_rota: int) -> List[Dict[str, Any]]:
    return _query(
        "SELECT escala, preco_centavos FROM Tarifa WHERE id_rota = ? ORDER BY preco_centavos",
        (id_rota,),
    )
