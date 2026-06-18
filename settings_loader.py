import json
from functools import lru_cache
from pathlib import Path


SETTINGS_PATH = Path(__file__).with_name("setting.json")


def _clean_string_list(values):
    cleaned = []
    seen = set()

    for value in values or []:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)

    return cleaned


@lru_cache(maxsize=1)
def load_settings():
    data = {}

    if SETTINGS_PATH.exists():
        with SETTINGS_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

    currencies = [value.upper() for value in _clean_string_list(data.get("currencies", []))]
    expense_groups = _clean_string_list(data.get("expense_groups", []))

    default_currency = "HKD" if "HKD" in currencies else (currencies[0] if currencies else None)
    default_expense_group = (
        "Others" if "Others" in expense_groups else (expense_groups[0] if expense_groups else None)
    )

    return {
        "currencies": currencies,
        "expense_groups": expense_groups,
        "default_currency": default_currency,
        "default_expense_group": default_expense_group,
    }


def normalize_currency(value):
    settings = load_settings()
    if value is None:
        return None

    text = str(value).strip().upper()
    if not text:
        return None

    return text if text in settings["currencies"] else None


def normalize_expense_group(value):
    settings = load_settings()
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    return text if text in settings["expense_groups"] else None
