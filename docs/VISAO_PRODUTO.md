# URUÁ-T — Visão de Produto e Diretrizes

> Documento de orientação do produto. Atualizado em 24/10/2026.

## 1. O que é o URUÁ-T

O URUÁ-T é um **aplicativo de monitoramento de embarcações fluviais** com atualizações
de posição a cada **5 segundos** (praticamente em tempo real), voltado ao contexto
ribeirinho da Amazônia (ex.: Oriximiná–PA).

**Missão:** permitir que o passageiro saiba, em tempo quase real, onde está a embarcação
com a qual deseja viajar — reduzindo incerteza e apoiando a logística fluvial.

## 2. Personas e Papéis

### 2.1 Passageiro (visitante / usuário cadastrado)
- **Não precisa de cadastro** para visualizar a localização das embarcações no mapa.
- O cadastro é necessário **apenas** para:
  - adquirir passagens;
  - solicitar informações ao responsável pela embarcação.
- Cadastro feito com **login (e-mail) e senha**.

### 2.2 Responsável de embarcação (Operador)
- Cadastra a embarcação com os dados obrigatórios:
  - **nome** da embarcação;
  - **trecho de navegação** (rota/portos de origem e destino);
  - **dias e horários** de cada trecho (grade de partidas);
  - **preços de passagem** por itinerário ou escala (escalas intermediárias).
- Cadastro **obrigatório** com login (e-mail) e senha, aos moldes do passageiro.

### 2.3 Administrador
- Gestão geral da plataforma (usuários, operadores, moderação de cadastros).

## 3. Regras de Autenticação

| Regra | Especificação |
|---|---|
| Login | **Exclusivamente por e-mail** (não há login por nome de usuário ou telefone) |
| Senha | Mínimo de **8 caracteres**, exigindo **múltiplos tipos de caracteres**: letras maiúsculas e minúsculas, dígitos e pelo menos um símbolo especial |
| Armazenamento | Somente hash (bcrypt/argon2) — nunca senha em texto puro |
| Sessão | JWT com expiração curta + refresh token (revalidar escopo por papel) |

> Nota: "no mínimo 8 múltiplos caracteres" foi interpretado como *mínimo 8 caracteres
> compostos por múltiplas classes de caracteres*. Confirmar com o dono do produto.

Validação de senha sugerida (backend):
```python
import re

def senha_valida(senha: str) -> bool:
    return (
        len(senha) >= 8
        and re.search(r"[A-Z]", senha) is not None
        and re.search(r"[a-z]", senha) is not None
        and re.search(r"\d", senha) is not None
        and re.search(r"[^\w\s]", senha) is not None
    )
```

## 4. Modelo de Dados Necessário (lacunas atuais)

O schema atual (`database/schema.sql`) possui `Usuario`, `Operador`, `Embarcacao` e
`Localizacao`. Para atender à visão de produto, faltam tabelas:

1. **Rota/Trecho** — origem, destino, distância km, escalas intermediárias.
2. **HorarioPartida / Grade** — dia da semana + horário de partida por rota.
3. **Tarifa/Preço** — preço por trecho/escala (passageiro x carga, meia-entrada).
4. **Passagem** — compra vinculada a passageiro, rota, partida e valor.
5. **Mensagem/Solicitação** — canal passageiro → responsável da embarcação.
6. Coluna `email_verificado`, `criado_em`, `hash` de senha na tabela `Usuario`
   (hoje `senha VARCHAR(255)` guarda literal `'hash_senha'` no seed — apenas placeholder).

## 5. Sugestões de Melhoria (benchmark de mercado)

Baseadas em aplicativos consolidados de rastreamento marítimo/fluvial
(MarineTraffic, VesselFinder, Flotilla, ShipX, apps de balsas e ferry operators):

### 5.1 Visualização e tempo real
- **WebSockets / SSE** em vez de polling a cada 5s — reduz latência e tráfego;
  manter polling como fallback.
- **Interpolação suave** da posição entre atualizações (dead reckoning) para o
  ícone deslizar no mapa em vez de "saltar".
- **Camadas do mapa**: rotas navegáveis, portos/terminais, áreas de fundeio,
  níveis do rio (boca-de-leite etc.).
- **Histórico de trajeto (playback)** com linha do tempo, como no MarineTraffic.
- **Busca direta** por nome/registro da embarcação e **favoritos/alertas**.

### 5.2 Informação operacional (o que o passageiro mais consulta)
- **ETA em tempo real** já calculado (`backend/calculo_eta.py`) — **integrar à API**
  via endpoint `GET /embarcacoes/{id}/eta?destino=...` e exibir no popup do mapa.
- **"Chegou / Está atrasado / Partiu"**: status da viagem por partida programada,
  comparando grade horária × posição atual.
- **Próxima partida** visível no card da embarcação (dia/hora/preço).
- **Distância restante** e velocidade desenvolvida (em nós e km/h — padrão do setor
  náutico é nó; converter e mostrar ambos).

### 5.3 Confiança e qualidade do dado
- Indicador de **idade do último sinal** ("posição atualizada há Xs") e marcação
  explícita de dados simulados vs. reais (evitar confundir simulação com GPS real).
- **Filtro de pontos absurdos** (GPS jump) e detecção de embarcação "fantasma"
  (sem sinal há N minutos → status offline).
- Prever degradação graciosa quando o backend estiver fora do ar (mapa com última
  posição conhecida + aviso, além dos toasts já existentes).

### 5.4 Passagens e comunicação
- Fluxo: mapa (público) → escolher embarcação/partida → login → seleção de assento
  ou quantidade → pagamento (Pix é essencial no contexto ribeirinho) → QR code do
  bilhete.
- **Notificações** (e-mail/WhatsApp/push): "embarcação saiu", "chegará em 30 min",
  "atraso informado pelo operador".
- Canal de **mensagem passageiro → operador** com histórico, atrelado à viagem.

### 5.5 Acessibilidade e contexto local
- **Modo offline / baixo consumo de dados**: comunidades ribeirinhas têm conexão
  instável — compactar payload (posições como array binário ou CSV), cache HTTP.
- Interface leve, mobile-first (já responsiva) e futura **versão PWA instalável**;
  considerar até um canal por SMS/WhatsApp como alternativa ao app.
- Idioma PT-BR simples; nomes de portos/trechos familiares à comunidade.

### 5.6 Segurança e conformidade
- Hash de senha (bcrypt/argon2), rate-limit nos endpoints de login, HTTPS.
- LGPD: minimizar dados de passageiros; log de acesso; exclusão de conta.
- Validação de entrada nas position reports (clamp de lat/lon) e CORS restrito.

## 6. Débitos técnicos conhecidos (para o backlog)

- `pytest` não está em `backend/requirements.txt` (testes existem mas não rodam
  no ambiente limpo).
- Lógica de movimento duplicada em `simular_movimento()` e `/simular-movimento`
  — extrair para uma função única.
- `@app.on_event("startup")` deprecado — migrar para `lifespan` do FastAPI.
- `__pycache__/` commitado — adicionar ao `.gitignore`.
- ETA isolado sem endpoint público (integração pendente).
- API usa estado em memória; `schema.sql` existe mas não há camada de persistência
  conectada (nem driver PostgreSQL nos requirements).

## 7. Roadmap sugerido

| Fase | Entrega |
|---|---|
| 1 | Autenticação (e-mail + senha forte, papéis), CRUD de embarcação/rotas/horários/tarifas pelo operador, persistência PostgreSQL |
| 2 | Endpoints de viagem: grade de partidas, tarifas, ETA integrado ao mapa, status "atraso/partida" |
| 3 | Passagem: compra com Pix, bilhete com QR, canal de mensagens passageiro↔operador |
| 4 | Tempo real avançado: WebSocket, interpolação, playback de histórico, alertas de chegada/atraso |
| 5 | PWA/offline-first, notificações, telemetria real (GPS/AIS) substituindo a simulação |
