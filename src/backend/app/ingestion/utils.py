from decimal import Decimal, InvalidOperation
from typing import Any


_DEFAULT_LIST_KEYS: tuple[str, ...] = (
    "items",
    "list",
    "result",
    "results",
    "payload",
    "data",
    "rows",
    "orders",
    "nomenclatures",
    "points",
    "balances",
)


def extract_items(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    """Best-effort extraction of a list of dict items from a Saby payload.

    Saby endpoints are not uniformly typed in our client, so we probe a small
    set of conventional keys. If none match, we fall back to the first list
    value encountered. Non-dict members are filtered out.
    """

    if payload is None:
        return []
    if isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = None
        for key in _DEFAULT_LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break
        if raw_items is None:
            for value in payload.values():
                if isinstance(value, list):
                    raw_items = value
                    break
        if raw_items is None:
            return []

    return [item for item in raw_items if isinstance(item, dict)]


def to_decimal(value: Any, default: Decimal = Decimal(0)) -> Decimal:
    """Parse string/number balance/qty values into Decimal, tolerating commas."""

    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "").replace(",", ".")
        if not cleaned:
            return default
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return default
    return default
