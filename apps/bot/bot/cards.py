"""Рендер карточки подтверждения операции."""

from copilot_shared import OperationDraft

_TYPE_LABEL = {
    "goods_receipt": "📥 Поступление товаров/услуг",
    "sales_invoice": "📤 Реализация",
    "expense_receipt": "🧾 Чек/подотчёт",
    "payment_order": "💳 Платёжное поручение",
}


def render_card(op: OperationDraft) -> str:
    lines = [_TYPE_LABEL.get(op.operation_type.value, op.operation_type.value)]
    cp = op.counterparty
    who = cp.name + (f" (ИНН {cp.tin})" if cp.tin else "")
    lines.append(f"Контрагент: {who}")
    if op.doc_number or op.doc_date:
        lines.append(f"Документ: № {op.doc_number or '—'} от {op.doc_date or '—'}")
    for it in op.items:
        lines.append(f"• {it.name} — {it.qty:g} × {it.price:,.0f} = {it.sum:,.0f} сум")
    lines.append(f"Итого: {op.totals.sum:,.0f} сум"
                 + (f" + НДС {op.totals.vat_sum:,.0f}" if op.totals.vat_sum else ""))
    if op.user_comment:
        lines.append(f"Комментарий: {op.user_comment}")
    lines.append(op.explanation)
    return "\n".join(lines)
