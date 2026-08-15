"""Кодирование query string для HTTP-сервиса 1С.

Регресс-защита находки интеграции 31.07.2026: сервис 1С не декодирует «+»
в пробел, поэтому пробелы обязаны уходить как %20 (httpx params= шлёт «+» —
не возвращаться к нему).
"""

from app.agent.onec_client import _qs


def test_space_encoded_as_percent20_not_plus():
    qs = _qs(query="Иванов Иван")
    assert "%20" in qs
    assert "+" not in qs


def test_utf8_percent_encoding():
    assert _qs(query="Иванов") == "?query=%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2"


def test_empty_and_none_params_dropped():
    assert _qs(tin=None, name="") == ""
    assert _qs(tin="123", name=None) == "?tin=123"


def test_multiple_params_keep_order():
    assert _qs(tin="123", name="ООО Ромашка").startswith("?tin=123&name=")
