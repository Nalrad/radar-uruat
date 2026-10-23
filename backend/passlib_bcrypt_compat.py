"""Compatibilidade com bcrypt >= 4.x para o passlib 1.7.4.

O passlib lê `bcrypt.__about__.__version__`, atributo removido a partir do
bcrypt 4.1 — sem este shim, CryptContext(schemes=["bcrypt"]) falha ao detectar
a versão do backend. Importar ANTES de qualquer uso de seguranca.py.
Referência: https://github.com/pypa/passlib/issues/64 (fix recomendado pelo
próprio maintainers do passlib).
"""

import bcrypt

if not hasattr(bcrypt, "__about__"):
    class _About:
        __version__ = getattr(bcrypt, "__version__", "4")

    bcrypt.__about__ = _About()
