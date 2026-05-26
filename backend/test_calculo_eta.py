from datetime import timedelta
from calculo_eta import calcular_eta, calcular_distancia
import pytest

def test_calcular_eta_velocidade_normal():
    # Distância de 10km, velocidade de 20km/h -> tempo deve ser 0.5 horas (30 minutos)
    resultado = calcular_eta(10, 20)
    assert resultado == timedelta(minutes=30)

def test_calcular_eta_barco_parado():
    # Se a velocidade for 0, o ETA deve ser None
    resultado = calcular_eta(10, 0)
    assert resultado is None

def test_calcular_distancia_dois_pontos():
    # Teste simples com a fórmula de Haversine entre dois pontos na Amazônia
    # Oriximiná: -1.7656, -55.8661
    # Óbidos: -1.9056, -55.5186
    dist = calcular_distancia(-1.7656, -55.8661, -1.9056, -55.5186)
    
    # A distância real em linha reta é cerca de 42km.
    # Vamos verificar se o cálculo retorna algo próximo (tolerância de 5km)
    assert 37 <= dist <= 47

def test_simulacao_completa_eta():
    """
    Este teste simula um cenário real sem precisar conectar no banco:
    Mockamos as posições de uma embarcação e um destino.
    """
    embarcacao_lat, embarcacao_lon = -1.7656, -55.8661 # Oriximiná
    destino_lat, destino_lon = -1.9056, -55.5186 # Óbidos
    velocidade = 15.0 # km/h
    
    distancia = calcular_distancia(embarcacao_lat, embarcacao_lon, destino_lat, destino_lon)
    eta = calcular_eta(distancia, velocidade)
    
    # Distância de ~42km / 15km/h = ~2.8 horas
    assert isinstance(eta, timedelta)
    assert 2 < eta.total_seconds() / 3600 < 4
