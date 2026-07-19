"""Определения инструментов агента (закрытый список = граница возможностей v1)."""

from copilot_shared import OperationDraft

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

ALL_TOOLS = [FIND_COUNTERPARTY, FIND_ITEM, CREATE_OPERATION]
