-- Inserção de dados de teste (DML)
INSERT INTO Usuario (nome, email, senha, tipo_usuario) 
VALUES ('Darlan Soares', 'darlan@email.com', 'hash_senha', 'Admin');

INSERT INTO Operador (id_usuario, empresa, telefone) 
VALUES (1, 'Navegação Oriximiná', '(93) 9999-9999');

INSERT INTO Embarcacao (id_operador, nome, tipo, capacidade) 
VALUES (1, 'Amazon Star', 'Turismo', 50);

-- Consulta SQL (Recuperar a última posição conhecida da embarcação)
SELECT e.nome, l.latitude, l.longitude, l.velocidade, l.horario_registro
FROM Embarcacao e
JOIN Localizacao l ON e.id_embarcacao = l.id_embarcacao
WHERE e.id_embarcacao = 1
ORDER BY l.horario_registro DESC
LIMIT 1;
