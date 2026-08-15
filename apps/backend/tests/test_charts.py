"""Рендер графиков: PNG на выходе, валидация длин, кириллица."""

import pytest
from pydantic import ValidationError

from app.agent.charts import ChartSpec, Series, render

PNG_MAGIC = b"\x89PNG"


@pytest.mark.parametrize("chart_type", ["line", "bar", "hbar"])
def test_renders_png(chart_type):
    spec = ChartSpec(
        chart_type=chart_type, title="Продажи по месяцам, млн сум",
        x_labels=["2026-05", "2026-06", "2026-07"],
        series=[Series(name="Выручка", values=[270e6, 480e6, 290e6])])
    png = render(spec)
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 1000


def test_multi_series_line():
    spec = ChartSpec(
        chart_type="line", title="Выручка и себестоимость",
        x_labels=["июнь", "июль"],
        series=[Series(name="Выручка", values=[480e6, 290e6]),
                Series(name="Себестоимость", values=[360e6, 227e6])])
    assert render(spec).startswith(PNG_MAGIC)


def test_length_mismatch_rejected():
    with pytest.raises(ValidationError, match="длины"):
        ChartSpec(chart_type="line", title="x", x_labels=["a", "b"],
                  series=[Series(name="s", values=[1.0])])
