"""Определения инструментов агента (закрытый список = граница возможностей v1)."""

from copilot_shared import OperationDraft

from .charts import ChartSpec

FIND_COUNTERPARTY = {
    "name": "find_counterparty",
    "description": (
        "Найти контрагента в справочнике 1С по ИНН/СТИР или части названия. "
        "Используй, чтобы проверить поставщика/покупателя и получить его код (ref_1c)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tin": {"type": "string", "description": "ИНН/СТИР, 9 цифр"},
            "name": {"type": "string", "description": "Часть наименования"},
        },
    },
}

FIND_ITEM = {
    "name": "find_item",
    "description": (
        "Найти номенклатуру в справочнике 1С по названию или ИКПУ. "
        "Используй, чтобы привязать позиции документа к справочнику (item_ref_1c)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Название товара/услуги или ИКПУ"},
        },
        "required": ["query"],
    },
}

FIND_EMPLOYEE = {
    "name": "find_employee",
    "description": (
        "Найти сотрудника (физлицо) в 1С по части ФИО. Нужен для чека подотчётного лица: "
        "подотчётника нельзя угадать или создать — его обязательно надо найти в базе. "
        "Если пользователь не назвал ФИО — сначала спроси, потом ищи. "
        "Если поиск ничего не вернул, честно скажи об этом и не создавай операцию."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Часть ФИО подотчётного лица"},
        },
        "required": ["query"],
    },
}

FIND_WAREHOUSE = {
    "name": "find_warehouse",
    "description": (
        "Получить список складов в 1С (можно с фильтром по названию). Вызывай один раз "
        "для операций с товарами: если склад ровно один — ничего не делай (1С подставит "
        "его сама, warehouse_ref оставь пустым); если складов несколько — спроси у "
        "пользователя, на какой склад, и подставь выбранный GUID в warehouse_ref."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Часть названия склада (можно пусто)"},
        },
    },
}

CREATE_OPERATION = {
    "name": "create_operation",
    "description": (
        "Собрать хозяйственную операцию и показать пользователю на подтверждение. "
        "Вызывай ТОЛЬКО когда собраны все обязательные реквизиты (контрагент, дата, суммы). "
        "После вызова система покажет пользователю карточку; фактическая отправка в 1С "
        "произойдёт после его подтверждения."
    ),
    "input_schema": OperationDraft.model_json_schema(),
}

# --- Аналитика (только чтение, ТЗ §4.7–4.9) ---

_PERIOD_PROPS = {
    "date_from": {"type": "string", "description": "Начало периода, ГГГГ-ММ-ДД"},
    "date_to": {"type": "string", "description": "Конец периода включительно, ГГГГ-ММ-ДД"},
}

GET_ACCOUNT_REPORT = {
    "name": "get_account_report",
    "description": (
        "Обороты и остатки по счёту бухучёта за период (эквивалент ОСВ). "
        "Шпаргалка по счетам НСБУ Узбекистана: 4010 — задолженность покупателей (ДЗ, "
        "«сколько нам должны»), 6010 — долг поставщикам (КЗ, «сколько мы должны»), "
        "9010 — выручка (кредитовый оборот), 9110 — себестоимость, 9420 — "
        "административные расходы, 9430 — прочие операционные расходы, 5010 — касса, "
        "5110 — расчётный счёт. group_by: subconto1 — разрез по аналитике "
        "(контрагенты/номенклатура/статьи), month — динамика по месяцам, "
        "none — только итог."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "account": {"type": "string", "description": "Код счёта, например 4010"},
            **_PERIOD_PROPS,
            "group_by": {"type": "string", "enum": ["none", "subconto1", "subconto2", "month"]},
            "limit": {"type": "integer", "description": "Строк разреза, по умолчанию 20"},
        },
        "required": ["account", "date_from", "date_to"],
    },
}

GET_SALES_REPORT = {
    "name": "get_sales_report",
    "description": (
        "Продажи по периодам: выручка без НДС, себестоимость, число документов. "
        "dimension=counterparty — разрез по покупателям; dimension=item — разрез по "
        "НОМЕНКЛАТУРНЫМ ГРУППАМ (не по отдельным товарам — так устроен учёт 9010 в "
        "1С; в ответах говори «группа товаров»). Ограничения реальной 1С: внутри "
        "breakdown поле cost всегда 0 (себестоимость не имеет этой аналитики — "
        "используй только cost итога периода) и qty может быть 0 (нет количественного "
        "учёта) — не делай выводов из этих нулей. Рецепт для «почему упали продажи»: "
        "сначала месяцы за полгода без разреза — найди провал; затем разрезы item и "
        "counterparty за упавший месяц и предыдущий — сравни. Периоды без продаж "
        "приходят с нулями."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            **_PERIOD_PROPS,
            "granularity": {"type": "string", "enum": ["month", "day"]},
            "dimension": {"type": "string", "enum": ["none", "item", "counterparty"]},
            "limit": {"type": "integer", "description": "Строк разреза на период, по умолчанию 10"},
        },
        "required": ["date_from", "date_to"],
    },
}

GET_CASH_REPORT = {
    "name": "get_cash_report",
    "description": ("Остатки денежных средств по кассам и банковским счетам на дату "
                    "(по умолчанию — сегодня). Валютные счета — с пересчётом в сумы."),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "ГГГГ-ММ-ДД, по умолчанию сегодня"},
        },
    },
}

RENDER_CHART = {
    "name": "render_chart",
    "description": (
        "Построить график к ответу — он уйдёт пользователю картинкой вместе с текстом. "
        "Вызывай, когда есть динамика по периодам (line) или топ категорий (hbar/bar) "
        "из 3+ точек. В values подставляй ТОЛЬКО числа из результатов инструментов "
        "этого диалога — никогда не выдумывай значения."
    ),
    "input_schema": ChartSpec.model_json_schema(),
}

ALL_TOOLS = [
    FIND_COUNTERPARTY, FIND_ITEM, FIND_EMPLOYEE, FIND_WAREHOUSE, CREATE_OPERATION,
    GET_ACCOUNT_REPORT, GET_SALES_REPORT, GET_CASH_REPORT, RENDER_CHART,
]
