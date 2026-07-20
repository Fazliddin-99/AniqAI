"""Рендер карточки подтверждения операции."""

from copilot_shared import OperationDraft

_TYPE_LABEL = {
    "goods_receipt": "📥 Поступление товаров/услуг",
    "sales_invoice": "📤 Реализация",
    "expense_receipt": "🧾 Чек подотчётника (Авансовый отчёт)",
    "payment_order": "💳 Платёжное поручение",
    "customs_declaration": "🛃 ГТД по импорту",
}


def _money(value: float, currency: str = "UZS") -> str:
    unit = "сум" if currency == "UZS" else currency
    return f"{value:,.0f} {unit}"


def render_card(op: OperationDraft) -> str:
    lines = [_TYPE_LABEL.get(op.operation_type.value, op.operation_type.value)]

    cp = op.counterparty
    who = cp.name + (f" (ИНН {cp.tin})" if cp.tin else "")
    # Для ГТД контрагент — иностранный поставщик, а не таможня: подписываем явно,
    # иначе бухгалтер решит, что бот перепутал стороны.
    label = "Поставщик" if op.customs_details else "Контрагент"
    lines.append(f"{label}: {who}")

    if op.expense_details:
        person = op.expense_details.accountable_person
        mark = "" if person.ref_1c else "  ⚠️ не найден в базе"
        lines.append(f"Подотчётное лицо: {person.name}{mark}")

    if op.doc_number or op.doc_date:
        lines.append(f"Документ: № {op.doc_number or '—'} от {op.doc_date or '—'}")

    for it in op.items:
        suffix = " (услуга)" if it.kind.value == "service" else ""
        lines.append(
            f"• {it.name}{suffix} — {it.qty:g} × {it.price:,.0f} = "
            f"{_money(it.sum, op.currency)}"
        )

    total = _money(op.totals.sum, op.currency)
    lines.append(f"Итого: {total}"
                 + (f" + НДС {op.totals.vat_sum:,.0f}" if op.totals.vat_sum else ""))

    if op.customs_details:
        lines.extend(_customs_lines(op))

    if op.user_comment:
        lines.append(f"Комментарий: {op.user_comment}")
    lines.append(op.explanation)
    return "\n".join(lines)


def _customs_lines(op: OperationDraft) -> list[str]:
    """Блок ГТД: платежи и предупреждение о создании второго документа."""
    cd = op.customs_details
    assert cd is not None

    duty = sum(s.duty_sum for s in cd.sections)
    fees = sum(s.fee_sum for s in cd.sections)
    vat = sum(s.vat_sum for s in cd.sections)

    lines = [
        f"ГТД № {cd.declaration_number} от {cd.declaration_date or op.doc_date or '—'}",
        f"Таможня: {cd.customs_office.name}",
        f"Пошлина: {duty:,.0f} сум · Сбор: {fees:,.0f} сум · НДС на таможне: {vat:,.0f} сум",
    ]
    if len(cd.sections) > 1:
        lines.append(f"Разделов ГТД: {len(cd.sections)}")
    lines.append("⚠️ Будет создано ДВА документа: поступление от поставщика и ГТД на его "
                 "основании. Если поступление уже заведено вручную — получится дубль.")
    return lines
