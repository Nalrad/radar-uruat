from datetime import timedelta
import math

def calcular_distancia(lat1, lon1, lat2, lon2):
    """
    Calcula a distância aproximada em km entre dois pontos geográficos
    usando a fórmula de Haversine.
    """
    R = 6371  # Raio da Terra em km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2) * math.sin(delta_phi/2) + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda/2) * math.sin(delta_lambda/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c

def calcular_eta(distancia_km, velocidade_kmh):
    """
    Calcula a Estimativa de Tempo de Chegada (ETA).
    Retorna um objeto timedelta.
    Se a velocidade for 0 ou negativa, retorna None (não chegará).
    """
    if velocidade_kmh <= 0:
        return None
    horas = distancia_km / velocidade_kmh
    return timedelta(hours=horas)
