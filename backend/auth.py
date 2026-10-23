"""Endpoints de autenticação e cadastro do operador — fase 2 do roadmap.

Cobre as seções 2.2 e 3 de docs/VISAO_PRODUTO.md:
- POST /auth/cadastro            (passageiro ou operador)
- POST /auth/login               (exclusivamente por e-mail; retorna JWT)
- GET  /auth/eu                  (perfil a partir do token)
- CRUD do operador: embarcações, rotas (trechos), partidas e tarifas.

Proteção: dependência `usuario_atual` decodifica o Bearer token; os endpoints
de gestão exigem papel 'operador' E propriedade do recurso (403 caso contrário).
"""

import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

import persistencia as db
from seguranca import (
    criar_token,
    email_valido,
    hash_senha,
    normalizar_email,
    senha_valida,
    verificar_senha,
    decodificar_token,
    TokenInvalido,
)

router = APIRouter(tags=["auth"])

RE_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ── Modelos de entrada/saída ─────────────────────────────────
class Cadastro(BaseModel):
    nome: str = Field(..., min_length=2, max_length=100)
    email: str
    senha: str
    papel: str = "passageiro"

    @field_validator("email")
    @classmethod
    def _valida_email(cls, v: str) -> str:
        if not email_valido(v):
            raise ValueError("e-mail inválido")
        return normalizar_email(v)

    @field_validator("senha")
    @classmethod
    def _valida_senha(cls, v: str) -> str:
        if not senha_valida(v):
            raise ValueError(
                "senha fraca: mínimo 8 caracteres com maiúscula, minúscula, dígito e símbolo"
            )
        return v

    @field_validator("papel")
    @classmethod
    def _valida_papel(cls, v: str) -> str:
        if v not in ("passageiro", "operador"):
            raise ValueError("papel deve ser 'passageiro' ou 'operador'")
        return v


class Login(BaseModel):
    email: str
    senha: str

    @field_validator("email")
    @classmethod
    def _normaliza(cls, v: str) -> str:
        return normalizar_email(v)


class TokenResposta(BaseModel):
    access_token: str
    token_type: str = "bearer"
    papel: str
    nome: str


class EmbarcacaoCadastro(BaseModel):
    nome: str = Field(..., min_length=2, max_length=100)
    tipo: str = "Transporte"
    velocidade_no: float = Field(default=8.0, ge=0, le=60)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class RotaCadastro(BaseModel):
    origem: str = Field(..., min_length=2, max_length=100)
    destino: str = Field(..., min_length=2, max_length=100)
    lat_origem: float = Field(..., ge=-90, le=90)
    lon_origem: float = Field(..., ge=-180, le=180)
    lat_destino: float = Field(..., ge=-90, le=90)
    lon_destino: float = Field(..., ge=-180, le=180)


class PartidaCadastro(BaseModel):
    dia_semana: int = Field(..., ge=0, le=6, description="0=segunda ... 6=domingo")
    hora: str = Field(..., description="Horário local no formato HH:MM")

    @field_validator("hora")
    @classmethod
    def _valida_hora(cls, v: str) -> str:
        if not RE_HORA.match(v):
            raise ValueError("hora deve estar no formato HH:MM (00:00–23:59)")
        return v


class TarifaCadastro(BaseModel):
    escala: Optional[str] = Field(default=None, max_length=50,
                                  description="Ex.: '1ª classe', 'tombolo'; omitir = preço único")
    preco_centavos: int = Field(..., ge=0, description="Preço em centavos de real")


# ── Dependências de autorização ──────────────────────────────
def usuario_atual(authorization: Optional[str] = Header(None)) -> dict:
    """Extrai e valida o Bearer token; 401 em qualquer falha."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Credencial ausente — envie 'Authorization: Bearer <token>'")
    try:
        claims = decodificar_token(authorization.split(" ", 1)[1])
    except TokenInvalido:
        raise HTTPException(401, "Token inválido ou expirado")
    usuario = db.usuario_por_id(int(claims["sub"]))
    if usuario is None:
        raise HTTPException(401, "Usuário não existe mais")
    return usuario


def operador_atual(usuario: dict = Depends(usuario_atual)) -> dict:
    if usuario["papel"] != "operador":
        raise HTTPException(403, "Acesso restrito a operadores")
    return usuario


def _checa_dono_embarcacao(id_embarcacao: int, operador: dict) -> dict:
    emb = db.embarcacao_por_id(id_embarcacao)
    if emb is None:
        raise HTTPException(404, "Embarcação não encontrada")
    if emb["id_operador"] != operador["id_usuario"]:
        raise HTTPException(403, "Esta embarcação pertence a outro operador")
    return emb


def _rota_com_ownership(id_rota: int, operador: dict) -> dict:
    """Partidas/tarifas são filhas da rota; validamos o dono via embarcação.

    404 se a rota não existe; 403 se existe mas é de outro operador — os dois
    casos não devem ser distinguíveis para quem não é dono? São: o id da rota
    só circula entre o próprio operador, então responder com clareza ajuda o
    suporte sem expor dados (nenhum conteúdo do recurso é retornado).
    """
    for emb in db.listar_embarcacoes():
        if emb["id_operador"] != operador["id_usuario"]:
            continue
        for rota in db.rotas_da_embarcacao(emb["id_embarcacao"]):
            if rota["id_rota"] == id_rota:
                return rota
    existe = any(r["id_rota"] == id_rota for r in db.todas_rotas())
    if not existe:
        raise HTTPException(404, "Rota não encontrada")
    raise HTTPException(403, "Rota pertence a outro operador")


# ── Auth ─────────────────────────────────────────────────────
@router.post("/auth/cadastro", status_code=201)
def cadastrar(dados: Cadastro):
    if db.usuario_por_email(dados.email) is not None:
        raise HTTPException(409, "Já existe um cadastro com este e-mail")
    id_usuario = db.inserir_usuario(dados.nome, dados.email, hash_senha(dados.senha), dados.papel)
    return {"id_usuario": id_usuario, "email": dados.email, "papel": dados.papel}


@router.post("/auth/login", response_model=TokenResposta)
def login(dados: Login):
    # Mensagem única para e-mail inexistente e senha errada: não revela
    # quais e-mails estão cadastrados (enumeração).
    usuario = db.usuario_por_email(dados.email)
    if usuario is None or not verificar_senha(dados.senha, usuario["hash_senha"]):
        raise HTTPException(401, "E-mail ou senha incorretos")
    return TokenResposta(
        access_token=criar_token(usuario["id_usuario"], usuario["email"], usuario["papel"]),
        papel=usuario["papel"],
        nome=usuario["nome"],
    )


@router.get("/auth/eu")
def meu_perfil(usuario: dict = Depends(usuario_atual)):
    return {k: usuario[k] for k in ("id_usuario", "nome", "email", "papel")}


# ── Gestão pelo operador ─────────────────────────────────────
gestao = APIRouter(prefix="/operador", tags=["operador"])


@gestao.post("/embarcacoes", status_code=201)
def criar_embarcacao(dados: EmbarcacaoCadastro, operador: dict = Depends(operador_atual)):
    id_emb = db.inserir_embarcacao(
        operador["id_usuario"], dados.nome, dados.tipo,
        dados.velocidade_no, dados.latitude, dados.longitude,
    )
    return {"id_embarcacao": id_emb, "nome": dados.nome}


@gestao.get("/embarcacoes")
def minhas_embarcacoes(operador: dict = Depends(operador_atual)):
    return [e for e in db.listar_embarcacoes() if e["id_operador"] == operador["id_usuario"]]


@gestao.post("/embarcacoes/{id_embarcacao}/rotas", status_code=201)
def criar_rota(id_embarcacao: int, dados: RotaCadastro,
               operador: dict = Depends(operador_atual)):
    _checa_dono_embarcacao(id_embarcacao, operador)
    id_rota = db.inserir_rota(
        id_embarcacao,
        unicodedata.normalize("NFC", dados.origem.strip()),
        unicodedata.normalize("NFC", dados.destino.strip()),
        dados.lat_origem, dados.lon_origem, dados.lat_destino, dados.lon_destino,
    )
    return {"id_rota": id_rota}


@gestao.post("/rotas/{id_rota}/partidas", status_code=201)
def criar_partida(id_rota: int, dados: PartidaCadastro,
                  operador: dict = Depends(operador_atual)):
    rota = _rota_com_ownership(id_rota, operador)
    id_partida = db.inserir_partida(rota["id_rota"], dados.dia_semana, dados.hora)
    return {"id_partida": id_partida}


@gestao.post("/rotas/{id_rota}/tarifas", status_code=201)
def criar_tarifa(id_rota: int, dados: TarifaCadastro,
                 operador: dict = Depends(operador_atual)):
    rota = _rota_com_ownership(id_rota, operador)
    escala = None if dados.escala is None else dados.escala.strip() or None
    id_tarifa = db.inserir_tarifa(rota["id_rota"], escala, dados.preco_centavos)
    return {"id_tarifa": id_tarifa}


router.include_router(gestao)
