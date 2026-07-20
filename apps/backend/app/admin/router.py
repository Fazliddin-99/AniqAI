"""Веб-админка: управление компаниями (с подключением к 1С) и пользователями.

Авторизация — один пароль ADMIN_PASSWORD, сессия в подписанной cookie
(SessionMiddleware). Доступ к спискам тех, кто пишет в базы 1С, закрыт логином.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..db import service
from ..db.session import get_session

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _authed(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _login_redirect() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, password: str = Form(...)):
    if password == os.environ.get("ADMIN_PASSWORD"):
        request.session["admin"] = True
        return RedirectResponse("/admin/companies", status_code=302)
    return templates.TemplateResponse(request, "login.html",
                                      {"error": "Неверный пароль"}, status_code=401)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return _login_redirect()


@router.get("", response_class=HTMLResponse)
def index(request: Request):
    return RedirectResponse("/admin/companies", status_code=302)


# --- Компании ---

@router.get("/companies", response_class=HTMLResponse)
def companies(request: Request):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        return templates.TemplateResponse(request, "companies.html",
                                          {"companies": service.list_companies(db)})
    finally:
        db.close()


@router.get("/companies/new", response_class=HTMLResponse)
def company_new(request: Request):
    if not _authed(request):
        return _login_redirect()
    return templates.TemplateResponse(request, "company_form.html", {"company": None})


@router.post("/companies")
def company_create(request: Request, name: str = Form(...), base_url: str = Form(...),
                   onec_user: str = Form(""), onec_password: str = Form("")):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        service.create_company(db, name, base_url, onec_user or None, onec_password or None)
    finally:
        db.close()
    return RedirectResponse("/admin/companies", status_code=302)


@router.get("/companies/{company_id}/edit", response_class=HTMLResponse)
def company_edit(request: Request, company_id: int):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        return templates.TemplateResponse(request, "company_form.html",
                                          {"company": service.get_company(db, company_id)})
    finally:
        db.close()


@router.post("/companies/{company_id}")
def company_update(request: Request, company_id: int, name: str = Form(...),
                   base_url: str = Form(...), onec_user: str = Form(""),
                   onec_password: str = Form(""), active: str = Form("on")):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        service.update_company(db, company_id, name=name, base_url=base_url,
                               onec_user=onec_user or None, onec_password=onec_password or None,
                               active=(active == "on"))
    finally:
        db.close()
    return RedirectResponse("/admin/companies", status_code=302)


# --- Пользователи ---

@router.get("/users", response_class=HTMLResponse)
def users(request: Request):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        return templates.TemplateResponse(request, "users.html",
                                          {"users": service.list_users(db)})
    finally:
        db.close()


@router.get("/users/new", response_class=HTMLResponse)
def user_new(request: Request):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        return templates.TemplateResponse(request, "user_form.html",
                                          {"companies": service.list_companies(db)})
    finally:
        db.close()


@router.post("/users")
def user_create(request: Request, telegram_user_id: int = Form(...),
                company_id: int = Form(...), name: str = Form(""), role: str = Form("accountant")):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        service.create_user(db, telegram_user_id, company_id, name, role)
    finally:
        db.close()
    return RedirectResponse("/admin/users", status_code=302)


@router.post("/users/{user_id}/toggle")
def user_toggle(request: Request, user_id: int, active: str = Form("false")):
    if not _authed(request):
        return _login_redirect()
    db = get_session()
    try:
        service.set_user_active(db, user_id, active == "true")
    finally:
        db.close()
    return RedirectResponse("/admin/users", status_code=302)
