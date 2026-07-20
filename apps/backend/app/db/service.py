"""Резолвинг пользователя и CRUD для админки. Шифрование учётных данных 1С прозрачно."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import crypto
from .models import Company, User


@dataclass
class OnecConn:
    base_url: str
    user: str | None
    password: str | None


@dataclass
class ResolvedUser:
    company_id: int
    company_name: str
    onec: OnecConn


def resolve_user(db: Session, telegram_user_id: int) -> ResolvedUser | None:
    """telegram_user_id → компания + расшифрованное подключение к 1С. None — доступа нет."""
    user = db.scalar(
        select(User).where(User.telegram_user_id == telegram_user_id, User.active.is_(True)))
    if user is None:
        return None
    c = user.company
    if c is None or not c.active:
        return None
    return ResolvedUser(
        company_id=c.id,
        company_name=c.name,
        onec=OnecConn(c.onec_base_url,
                      crypto.decrypt(c.onec_user_enc),
                      crypto.decrypt(c.onec_password_enc)),
    )


# --- CRUD для админки ---

def list_companies(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.id)))


def get_company(db: Session, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def create_company(db: Session, name: str, base_url: str,
                   onec_user: str | None, onec_password: str | None) -> Company:
    c = Company(name=name, onec_base_url=base_url,
                onec_user_enc=crypto.encrypt(onec_user),
                onec_password_enc=crypto.encrypt(onec_password))
    db.add(c)
    db.commit()
    return c


def update_company(db: Session, company_id: int, *, name: str, base_url: str,
                   onec_user: str | None, onec_password: str | None,
                   active: bool) -> None:
    c = db.get(Company, company_id)
    if c is None:
        return
    c.name, c.onec_base_url, c.active = name, base_url, active
    c.onec_user_enc = crypto.encrypt(onec_user)
    if onec_password:  # пустое поле пароля при редактировании — не затирать
        c.onec_password_enc = crypto.encrypt(onec_password)
    db.commit()


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


def create_user(db: Session, telegram_user_id: int, company_id: int,
                name: str, role: str = "accountant") -> User:
    u = User(telegram_user_id=telegram_user_id, company_id=company_id, name=name, role=role)
    db.add(u)
    db.commit()
    return u


def set_user_active(db: Session, user_id: int, active: bool) -> None:
    u = db.get(User, user_id)
    if u is not None:
        u.active = active
        db.commit()
