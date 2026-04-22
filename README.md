# URUÁ-T: Sistema de Monitoramento de Embarcações

O URUÁ-T é uma aplicação web desenvolvida com o objetivo de melhorar a visibilidade e a comunicação no transporte fluvial, especialmente em regiões ribeirinhas como Oriximiná (PA).

A proposta do sistema é permitir o acompanhamento de embarcações em um mapa interativo, contribuindo para uma melhor organização do transporte, apoio à logística local e maior acesso à informação pelas comunidades.

##  Tecnologias utilizadas

- Python
- FastAPI
- HTML, CSS e JavaScript
- Leaflet (mapas interativos)
- Uvicorn

##  Funcionalidades

- Visualização de embarcações em tempo quase real
- Mapa interativo com atualização automática
- Simulação de movimentação das embarcações
- Interface simples e acessível

##  Como executar o projeto

1. Clone o repositório:
```bash
git clone https://github.com/Nalrad/radar-amazonico

cd backend
source ../venv/bin/activate
uvicorn main:app --reload
http://127.0.0.1:8000/static/index.html

## Objetivo do projeto

Este projeto faz parte de uma ação de extensão, buscando aplicar conhecimentos de desenvolvimento web na solução de problemas reais, promovendo impacto social positivo.

## Contexto

O transporte fluvial é essencial em diversas regiões da Amazônia, e a falta de ferramentas digitais limita a comunicação e o acompanhamento das embarcações. O URUÁ-T surge como uma solução simples e acessível para esse cenário.


## Demonstração

![Mapa do sistema](docs/mapa_urua-t.png)
