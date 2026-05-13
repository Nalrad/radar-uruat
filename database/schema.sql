-- Criação da tabela de Usuários
CREATE TABLE Usuario (
    id_usuario SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    senha VARCHAR(255) NOT NULL,
    tipo_usuario VARCHAR(20)
);

-- Criação da tabela de Operadores
CREATE TABLE Operador (
    id_operador SERIAL PRIMARY KEY,
    id_usuario INT REFERENCES Usuario(id_usuario),
    empresa VARCHAR(100),
    telefone VARCHAR(20)
);

-- Criação da tabela de Embarcações
CREATE TABLE Embarcacao (
    id_embarcacao SERIAL PRIMARY KEY,
    id_operador INT REFERENCES Operador(id_operador),
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(50),
    capacidade INT,
    registro_maritimo VARCHAR(50)
);

-- Criação da tabela de Localização (Rastreamento)
CREATE TABLE Localizacao (
    id_localizacao SERIAL PRIMARY KEY,
    id_embarcacao INT REFERENCES Embarcacao(id_embarcacao),
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    velocidade FLOAT,
    horario_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
