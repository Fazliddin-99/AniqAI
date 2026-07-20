"""Симметричное шифрование учётных данных 1С в БД (Fernet).

Ключ — только в окружении (APP_ENCRYPTION_KEY), не в БД. Компрометация БД без ключа
не раскрывает пароли 1С.
"""

import os

from cryptography.fernet import Fernet

_GEN_HINT = ('APP_ENCRYPTION_KEY не задан. Сгенерируйте: '
             'uv run python -c "from cryptography.fernet import Fernet;'
             'print(Fernet.generate_key().decode())"')


def _fernet() -> Fernet:
    key = os.environ.get("APP_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(_GEN_HINT)
    return Fernet(key.encode())


def encrypt(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    return _fernet().decrypt(token.encode()).decode()
