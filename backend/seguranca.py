"""Autenticação do URUÁ-T — fase 2 do roadmap (docs/VISAO_PRODUTO.md §3).

Regras implementadas:
- Login exclusivamente por e-mail validado.
- Senha com no mínimo 8 caracteres e múltiplas classes (maiúscula, minúscula,
  dígito e símbolo) — interpretação registrada no documento de visão.
- Armazenamento apenas com hash bcrypt (nunca texto puro).
- Sessão via JWT (HS256) com expiração curta; papel ('passageiro' | 'operador')
  dentro das claims para revalidação de escopo em cada requisição.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import re
import secrets
import unicodedata

import jwt
from email_validator import EmailNotValidError, validate_email

import passlib_bcrypt_compat  # noqa: F401  shim p/ bcrypt>=4 + passlib 1.7.4
from passlib.context import CryptContext

ALGORITMO_JWT = "HS256"
DURACAO_TOKEN_MINUTOS = 60  # expiração curta, conforme docs §3

_roles_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Segredo do JWT: em produção vem de JWT_SECRET; em dev usa valor fixo com aviso.
JWT_SECRET = os.environ.get("JWT_SECRET") or "urua-t-dev-secret-trocar-em-producao"
if not os.environ.get("JWT_SECRET"):
    print("[AVISO] JWT_SECRET não definido — usando segredo de desenvolvimento.")


def _bcrypt_hash(senha: str) -> str:
    """Hash bcrypt com pré-processamento determinístico.

    O bcrypt trunca silenciosamente entradas acima de 72 bytes; o SHA-256 da
    senha em hex (64 chars ASCII) garante entrada uniforme e sem a fronteira
    problemática, permitindo senhas longas e unicode com segurança.
    """
    digest = hashlib.sha256(senha.encode("utf-8")).hexdigest()
    return _roles_ctx.hash(digest)


def hash_senha(senha: str) -> str:
    return _bcrypt_hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    try:
        return _roles_ctx.verify(hashlib.sha256(senha.encode("utf-8")).hexdigest(), hash_)
    except ValueError:
        return False


def normalizar_email(email: str) -> str:
    """Normaliza unicode (NFC) e caixa baixa — teclados móveis podem enviar
    formas decompostas ou maiúsculas; o login é sempre comparado normalizado."""
    return unicodedata.normalize("NFC", email.strip()).lower()


def email_valido(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


RE_MAIUSCULA = re.compile(r"[A-ZÀ-ÖØ-Þ]")
RE_MINUSCULA = re.compile(r"[a-zà-öø-ÿ]")
RE_DIGITO = re.compile(r"\d")
RE_SIMBOLO = re.compile(r"[^\w\s]", re.UNICODE)


def senha_valida(senha: str) -> bool:
    """Mínimo de 8 caracteres com múltiplas classes (docs §3)."""
    return (
        len(senha) >= 8
        and RE_MAIUSCULA.search(senha) is not None
        and RE_MINUSCULA.search(senha) is not None
        and RE_DIGITO.search(senha) is not None
        and RE_SIMBOLO.search(senha) is not None
    )


def criar_token(usuario_id: int, email: str, papel: str) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "email": email,
        "papel": papel,
        "iat": agora,
        "exp": agora + timedelta(minutes=DURACAO_TOKEN_MINUTOS),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITMO_JWT)


class TokenInvalido(Exception):
    pass


def decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITMO_JWT])
    except jwt.PyJWTError as exc:
        raise TokenInvalido(str(exc)) from exc
