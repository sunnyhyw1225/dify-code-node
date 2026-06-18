import json


def main(
    normalized_prediction,
    normalized_llm_field_confidence,
    history_features,
    field_sources,
    settings_json=None,
    currencies=None,
    expense_groups=None,
):
    def clean_string_list(values):
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

    def parse_json_maybe(value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return default
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return default
        return default

    def clamp(value, lo=0.0, hi=1.0):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        return max(lo, min(hi, value))

    def safe_float_or_none(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def get_nested_value(obj, dotted_key):
        current = obj
        for part in dotted_key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def load_settings_inline(settings_payload, currency_values, expense_group_values):
        data = parse_json_maybe(settings_payload, {})
        if not isinstance(data, dict):
            data = {}

        currencies = {
            value.upper()
            for value in clean_string_list(
                currency_values if currency_values is not None else data.get("currencies", [])
            )
        }
        expense_groups = set(
            clean_string_list(
                expense_group_values
                if expense_group_values is not None
                else data.get("expense_groups", [])
            )
        )

        return {
            "currencies": currencies,
            "expense_groups": expense_groups,
        }

    def normalize_currency(value):
        settings = load_settings_inline(settings_json, currencies, expense_groups)
        if value is None:
            return None

        text = str(value).strip().upper()
        if not text:
            return None

        return text if text in settings["currencies"] else None

    def normalize_expense_group(value):
        settings = load_settings_inline(settings_json, currencies, expense_groups)
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        return text if text in settings["expense_groups"] else None

    def mode_by_score(field, score):
        if score >= 0.85:
            return "prefill"
        if score >= 0.60:
            return "suggestion"
        return "manual"

    pred = parse_json_maybe(normalized_prediction, {})
    llm = parse_json_maybe(normalized_llm_field_confidence, {})
    feat = parse_json_maybe(history_features, {})
    sources = parse_json_maybe(field_sources, {})

    source_base_scores = {
        "receipt_explicit": 0.96,
        "receipt_inferred": 0.84,
        "context_explicit": 0.90,
        "context_inferred": 0.72,
        "llm": 0.62,
        "history_stable": 0.80,
        "history_default": 0.60,
        "rule": 0.93,
        "missing": 0.0,
    }

    fields = [
        "submitted_to.type",
        "submitted_to.target",
        "contact_number",
        "supervisor_advisor_faculty",
        "expense_detail.expense_group",
        "expense_detail.business_purpose",
        "expense_detail.expense_description",
        "expense_detail.currency",
        "expense_detail.amount",
        "expense_detail.book_rate",
        "expense_detail.equivalent_hkd_amount",
        "expense_detail.attach_receipt",
        "expense_detail.declare_if_no_receipt",
    ]

    field_scores = {}

    for field in fields:
        value = get_nested_value(pred, field)
        source = sources.get(field, "missing")

        if value is None or value == "":
            if field == "expense_detail.declare_if_no_receipt":
                attach_receipt = get_nested_value(pred, "expense_detail.attach_receipt")
                if attach_receipt is True:
                    field_scores[field] = 0.93
                else:
                    field_scores[field] = 0.0
            else:
                field_scores[field] = 0.0
            continue

        base = source_base_scores.get(source, 0.40)
        llm_conf = clamp(llm.get(field, 0.5))
        field_scores[field] = clamp((0.80 * base) + (0.20 * llm_conf))

    currency = get_nested_value(pred, "expense_detail.currency")
    if currency and normalize_currency(currency) is None:
        field_scores["expense_detail.currency"] = 0.0

    expense_group = get_nested_value(pred, "expense_detail.expense_group")
    if expense_group and normalize_expense_group(expense_group) is None:
        field_scores["expense_detail.expense_group"] = 0.0

    amount = safe_float_or_none(get_nested_value(pred, "expense_detail.amount"))
    amount_source = sources.get("expense_detail.amount", "missing")
    if amount is None:
        field_scores["expense_detail.amount"] = 0.0
    elif amount_source == "receipt_explicit":
        field_scores["expense_detail.amount"] = max(
            field_scores.get("expense_detail.amount", 0.0),
            0.92,
        )
    else:
        stats = feat.get("amount_stats_by_expense_group", {}).get(expense_group) or feat.get(
            "amount_stats",
            {},
        )
        p25 = safe_float_or_none(stats.get("p25")) if isinstance(stats, dict) else None
        p75 = safe_float_or_none(stats.get("p75")) if isinstance(stats, dict) else None
        if p25 is not None and p75 is not None and not (p25 <= amount <= p75):
            field_scores["expense_detail.amount"] = min(
                field_scores.get("expense_detail.amount", 0.0),
                0.60,
            )

    book_rate = safe_float_or_none(get_nested_value(pred, "expense_detail.book_rate"))
    equivalent = safe_float_or_none(get_nested_value(pred, "expense_detail.equivalent_hkd_amount"))

    if currency == "HKD" and book_rate == 1.0:
        field_scores["expense_detail.book_rate"] = max(
            field_scores.get("expense_detail.book_rate", 0.0),
            0.95,
        )

    if amount is not None and book_rate is not None and equivalent is not None:
        expected = round(amount * book_rate, 2)
        actual = round(equivalent, 2)
        if expected == actual:
            field_scores["expense_detail.equivalent_hkd_amount"] = max(
                field_scores.get("expense_detail.equivalent_hkd_amount", 0.0),
                0.92,
            )
        else:
            field_scores["expense_detail.equivalent_hkd_amount"] = 0.25

    attach_receipt = get_nested_value(pred, "expense_detail.attach_receipt")
    if attach_receipt is True:
        field_scores["expense_detail.attach_receipt"] = max(
            field_scores.get("expense_detail.attach_receipt", 0.0),
            0.92,
        )

    declaration = get_nested_value(pred, "expense_detail.declare_if_no_receipt")
    if attach_receipt is True and declaration == "":
        field_scores["expense_detail.declare_if_no_receipt"] = 0.93

    display_mode = {
        field: mode_by_score(field, score)
        for field, score in field_scores.items()
    }

    if display_mode.get("expense_detail.business_purpose") == "prefill":
        display_mode["expense_detail.business_purpose"] = "suggestion"

    if display_mode.get("submitted_to.target") == "prefill":
        display_mode["submitted_to.target"] = "suggestion"

    weights = {
        "expense_detail.amount": 1.6,
        "expense_detail.currency": 1.3,
        "expense_detail.expense_description": 1.2,
        "expense_detail.expense_group": 1.2,
        "expense_detail.attach_receipt": 1.0,
        "expense_detail.business_purpose": 1.1,
    }

    numerator = 0.0
    denominator = 0.0
    for field, score in field_scores.items():
        weight = weights.get(field, 1.0)
        numerator += weight * score
        denominator += weight

    overall_score = clamp(numerator / denominator if denominator else 0.0)

    return {
        "field_scores": json.dumps(field_scores, ensure_ascii=False),
        "overall_score": str(round(overall_score, 4)),
        "display_mode": json.dumps(display_mode, ensure_ascii=False),
        "field_sources": json.dumps(sources, ensure_ascii=False),
    }
