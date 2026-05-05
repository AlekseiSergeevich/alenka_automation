"""Простые эвристики по полям номенклатуры Sbis / Saby Retail."""


def is_sbis_internal_nom_code(value: object) -> bool:
    """Внутренний код номенклатуры вида ``X4924446`` (точнее: ``X`` + только цифры)."""

    if value is None:
        return False
    s = str(value).strip()
    return len(s) >= 2 and s[0] in ("x", "X") and s[1:].isdigit()
