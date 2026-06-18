import json

def main(
    normalized_prediction: str,
    normalized_llm_field_confidence: str,
    history_features: str,
    field_sources: str
):
    def parse_json_maybe(value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return default

    def clamp(x, lo=0.0, hi=1.0):
        try:
            x = float(x)
        except (TypeError, ValueError):
            x = 0.0
        return max(lo, min(hi, x))

    def safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def get_nested_value(obj, dotted_key):
        cur = obj
        for part in dotted_key.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    def mode_by_score(score: float) -> str:
        if score >= 0.88:
            return "prefill"
        if score >= 0.60:
            return "suggestion"
        return "manual"

    pred = parse_json_maybe(normalized_prediction, {})
    llm = parse_json_maybe(normalized_llm_field_confidence, {})
    feat = parse_json_maybe(history_features, {})
    sources = parse_json_maybe(field_sources, {})

    field_scores = {}

    source_base_scores = {
        "context_explicit": 0.95,
        "context_inferred": 0.78,
        "llm": 0.70,
        "history_stable": 0.82,
        "history_default": 0.62,
        "rule": 0.90,
        "missing": 0.0
    }

    def score_from_source(field, default_source="missing"):
        source = sources.get(field, default_source)
        base = source_base_scores.get(source, 0.3)
        llm_conf = clamp(llm.get(field, 0.5))

        # Blend source reliability with LLM confidence
        return clamp((0.75 * base) + (0.25 * llm_conf))

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

    for field in fields:
        value = get_nested_value(pred, field)

        if value is None or value == "":
            if field == "expense_detail.declare_if_no_receipt":
                attach_receipt = get_nested_value(pred, "expense_detail.attach_receipt")
                if attach_receipt is True:
                    # Empty declaration is correct when receipt is attached.
                    field_scores[field] = score_from_source(field, "rule")
                else:
                    field_scores[field] = 0.0
            else:
                field_scores[field] = 0.0
        else:
            field_scores[field] = score_from_source(field)

    # Extra validation: currency
    currency = get_nested_value(pred, "expense_detail.currency")
    common_currency = feat.get("common_currency", "HKD")

    if currency == common_currency:
        field_scores["expense_detail.currency"] = max(
            field_scores.get("expense_detail.currency", 0.0),
            0.88
        )

    # Extra validation: amount
    amount = get_nested_value(pred, "expense_detail.amount")

    if amount is None:
        field_scores["expense_detail.amount"] = 0.0
    else:
        amount_float = safe_float(amount, 0.0)
        expense_group = get_nested_value(pred, "expense_detail.expense_group")
        group_stats_all = feat.get("amount_stats_by_expense_group", {})
        group_stats = group_stats_all.get(expense_group, {})
        if group_stats and group_stats.get("count", 0) >= 2:
            stats = group_stats
        else:
            stats = feat.get("amount_stats", {})
        p25 = safe_float(stats.get("p25", 80.0), 80.0)
        p75 = safe_float(stats.get("p75", 300.0), 300.0)

        if p25 <= amount_float <= p75:
            field_scores["expense_detail.amount"] = min(
                max(field_scores.get("expense_detail.amount", 0.0), 0.65),
                0.84
            )
        else:
            field_scores["expense_detail.amount"] = min(
                field_scores.get("expense_detail.amount", 0.0),
                0.55
            )

    # Extra validation: equivalent HKD amount
    amount = get_nested_value(pred, "expense_detail.amount")
    book_rate = get_nested_value(pred, "expense_detail.book_rate")
    equivalent = get_nested_value(pred, "expense_detail.equivalent_hkd_amount")

    if amount is not None and book_rate is not None and equivalent is not None:
        expected = round(safe_float(amount) * safe_float(book_rate), 2)
        actual = round(safe_float(equivalent), 2)

        if expected == actual:
            field_scores["expense_detail.equivalent_hkd_amount"] = max(
                field_scores.get("expense_detail.equivalent_hkd_amount", 0.0),
                0.88
            )
        else:
            field_scores["expense_detail.equivalent_hkd_amount"] = 0.25

    # Extra validation: book_rate
    if currency == "HKD" and book_rate == 1.0:
        field_scores["expense_detail.book_rate"] = max(
            field_scores.get("expense_detail.book_rate", 0.0),
            0.90
        )

    # Extra validation: receipt declaration
    attach_receipt = get_nested_value(pred, "expense_detail.attach_receipt")
    declaration = get_nested_value(pred, "expense_detail.declare_if_no_receipt")

    if attach_receipt is True and declaration == "":
        field_scores["expense_detail.declare_if_no_receipt"] = 0.90
    elif attach_receipt is False and declaration:
        field_scores["expense_detail.declare_if_no_receipt"] = max(
            field_scores.get("expense_detail.declare_if_no_receipt", 0.0),
            0.75
        )

    # Policy override: amount should never auto-prefill
    display_mode = {
        field: mode_by_score(score)
        for field, score in field_scores.items()
    }

    if display_mode.get("expense_detail.amount") == "prefill":
        display_mode["expense_detail.amount"] = "suggestion"

    # Policy override: event-specific text should not prefill unless very strong
    for field in [
        "expense_detail.business_purpose",
        "expense_detail.expense_description"
    ]:
        if display_mode.get(field) == "prefill":
            display_mode[field] = "suggestion"

    # Weighted overall
    weights = {
        "expense_detail.amount": 1.5,
        "expense_detail.currency": 1.2,
        "expense_detail.attach_receipt": 1.1,
        "expense_detail.business_purpose": 1.2,
        "expense_detail.expense_description": 1.2,
    }

    num, den = 0.0, 0.0

    for field, score in field_scores.items():
        w = safe_float(weights.get(field, 1.0), 1.0)
        num += w * score
        den += w

    overall_score = clamp(num / den if den else 0.0)

    return {
        "field_scores": json.dumps(field_scores, ensure_ascii=False),
        "overall_score": str(round(overall_score, 4)),
        "display_mode": json.dumps(display_mode, ensure_ascii=False),
        "field_sources": json.dumps(sources, ensure_ascii=False)
    }