"""Рендер графиков к ответам аналитики: ChartSpec → PNG.

OO-API matplotlib (Figure + Agg-канвас) вместо pyplot: агентные ходы выполняются
в asyncio.to_thread, а pyplot держит глобальное состояние и непотокобезопасен.
"""

import io
from typing import Literal

from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from pydantic import BaseModel, Field, model_validator


class Series(BaseModel):
    name: str
    values: list[float] = Field(min_length=1)


class ChartSpec(BaseModel):
    chart_type: Literal["line", "bar", "hbar"]
    title: str
    x_labels: list[str] = Field(min_length=1, description="Подписи точек/категорий")
    series: list[Series] = Field(min_length=1, max_length=5)
    y_label: str | None = None

    @model_validator(mode="after")
    def _lengths_match(self) -> "ChartSpec":
        for s in self.series:
            if len(s.values) != len(self.x_labels):
                raise ValueError(
                    f"серия «{s.name}»: {len(s.values)} значений при "
                    f"{len(self.x_labels)} подписях — длины должны совпадать")
        return self


def _fmt_thousands(x: float, _pos) -> str:
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:,.0f} млн".replace(",", " ")
    return f"{x:,.0f}".replace(",", " ")


def render(spec: ChartSpec) -> bytes:
    fig = Figure(figsize=(10, 6), dpi=100)
    ax = fig.add_subplot()

    n = len(spec.x_labels)
    idx = range(n)
    if spec.chart_type == "line":
        for s in spec.series:
            ax.plot(idx, s.values, marker="o", linewidth=2, label=s.name)
        ax.set_xticks(idx)
        ax.set_xticklabels(spec.x_labels, rotation=45, ha="right")
        ax.yaxis.set_major_formatter(FuncFormatter(_fmt_thousands))
    elif spec.chart_type == "bar":
        width = 0.8 / len(spec.series)
        for i, s in enumerate(spec.series):
            ax.bar([x + i * width for x in idx], s.values, width=width, label=s.name)
        ax.set_xticks([x + 0.4 - width / 2 for x in idx])
        ax.set_xticklabels(spec.x_labels, rotation=45, ha="right")
        ax.yaxis.set_major_formatter(FuncFormatter(_fmt_thousands))
    else:  # hbar — топы, первый элемент сверху
        s = spec.series[0]
        ax.barh(list(idx), s.values)
        ax.set_yticks(list(idx))
        ax.set_yticklabels(spec.x_labels)
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(FuncFormatter(_fmt_thousands))

    ax.set_title(spec.title)
    if spec.y_label:
        ax.set_ylabel(spec.y_label)
    if len(spec.series) > 1:
        ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()
