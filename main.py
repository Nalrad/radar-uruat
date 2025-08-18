from fastapi import FastAPI
from typing import List
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import asyncio
import random

app = FastAPI()

# Modelo de dados
class Embarcacao(BaseModel):
    id: int
    nome: str
    tipo: str
    velocidade: float
    bandeira: str
    latitude: float
    longitude: float

# Lista inicial de embarcações
embarcacoes = [
    Embarcacao(id=1, nome="Barco Solimões", tipo="Transporte", velocidade=9.5, bandeira="Brasil", latitude=-3.13, longitude=-60.02),
    Embarcacao(id=2, nome="Amazon Star", tipo="Turismo", velocidade=6.2, bandeira="Brasil", latitude=-3.11, longitude=-60.03),
]

# Rota para listar embarcações
@app.get("/embarcacoes", response_model=List[Embarcacao])
def listar_embarcacoes():
    return embarcacoes

# Servir o HTML com mapa
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Função que simula o movimento (rodando em background)
async def simular_movimento():
    while True:
        for embarcacao in embarcacoes:
            embarcacao.latitude += random.uniform(-0.001, 0.001)
            embarcacao.longitude += random.uniform(-0.001, 0.001)
        await asyncio.sleep(5)  # Atualiza a cada 5 segundos

# Evento de inicialização para rodar a simulação automaticamente
@app.on_event("startup")
async def iniciar_simulacao():
    asyncio.create_task(simular_movimento())

# Endpoint POST para simular movimento manualmente
@app.post("/simular-movimento")
def simular_movimento_manual():
    for embarcacao in embarcacoes:
        embarcacao.latitude += random.uniform(-0.001, 0.001)
        embarcacao.longitude += random.uniform(-0.001, 0.001)
    return {"status": "Movimento simulado manualmente"}
