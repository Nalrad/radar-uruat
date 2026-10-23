-- URUÁ-T — esquema PostgreSQL alvo (produção).
-- Espelha backend/persistencia.py (SQLite da fase 2); a camada Python usa
-- SQLite enquanto o deploy não tem Postgres — os nomes/semânticas são idênticos.
-- Atualizado na fase 2 do roadmap (docs/VISAO_PRODUTO.md §4/§7): adiciona
-- Rota, Partida e Tarifa (grade de partidas, preços por escala).

-- Usuários: login exclusivamente por e-mail; senha apenas como hash (bcrypt).
CREATE TABLE Usuario (
    id_usuario SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hash_senha VARCHAR(255) NOT NULL,
    papel VARCHAR(20) NOT NULL CHECK (papel IN ('passageiro', 'operador'))
);

-- Embarcações pertencem a um operador (usuário com papel 'operador').
CREATE TABLE Embarcacao (
    id_embarcacao SERIAL PRIMARY KEY,
    id_operador INT REFERENCES Usuario(id_usuario),
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(50),
    velocidade_no REAL DEFAULT 0,        -- velocidade desenvolvida (nós)
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    rumo REAL DEFAULT 0                  -- heading 0-360
);

-- Trecho de navegação cadastrado pelo operador.
CREATE TABLE Rota (
    id_rota SERIAL PRIMARY KEY,
    id_embarcacao INT NOT NULL REFERENCES Embarcacao(id_embarcacao),
    origem VARCHAR(100) NOT NULL,
    destino VARCHAR(100) NOT NULL,
    lat_destino DOUBLE PRECISION NOT NULL,
    lon_destino DOUBLE PRECISION NOT NULL
);

-- Grade de partidas: dia da semana (0=segunda) + horário local 'HH:MM'.
CREATE TABLE Partida (
    id_partida SERIAL PRIMARY KEY,
    id_rota INT NOT NULL REFERENCES Rota(id_rota),
    dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    hora TIME NOT NULL
);

-- Preço da passagem por itinerário/escala; dinheiro em CENTAVOS.
CREATE TABLE Tarifa (
    id_tarifa SERIAL PRIMARY KEY,
    id_rota INT NOT NULL REFERENCES Rota(id_rota),
    escala VARCHAR(50),                  -- NULL = preço único
    preco_centavos INT NOT NULL CHECK (preco_centavos >= 0)
);

-- Rastreamento: histórico alimenta playback e "atualizado há Xs" (fase 4+).
CREATE TABLE Localizacao (
    id_localizacao SERIAL PRIMARY KEY,
    id_embarcacao INT REFERENCES Embarcacao(id_embarcacao),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    velocidade REAL,
    rumo REAL,
    horario_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_localizacao_embarcacao_data
    ON Localizacao (id_embarcacao, horario_registro DESC);
CREATE INDEX idx_rota_embarcacao ON Rota (id_embarcacao);
CREATE INDEX idx_partida_rota ON Partida (id_rota, dia_semana, hora);
