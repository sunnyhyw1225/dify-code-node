import json
import re

def main(llm_raw_output: str, history_features: str):
    def strip_fence(text: str) -> str:
        t = text.strip()
        t = re.sub(r'^```[a-zA-Z]*\n?', '', t)
        t = re.sub(r'\n?```$', '', t)
        return t.strip()

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

    def safe_float_or_none(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    raw = strip_fence(llm_raw_output)
    obj = json.loads(raw)

    feat = parse_json_maybe(history_features, {})

    predicted_input = obj.get("predicted_input", {})
    llm_field_confidence = obj.get("llm_field_confidence", {})
    explanations = obj.get("explanations", [])

    field_sources = {}

    # submitted_to
    submitted = predicted_input.setdefault("submitted_to", {})

    if submitted.get("type"):
        field_sources["submitted_to.type"] = "llm"
    else:
        submitted["type"] = feat.get("common_submitted_to_type", "Department")
        field_sources["submitted_to.type"] = "history_default"

    if submitted.get("target"):
        field_sources["submitted_to.target"] = "llm"
    else:
        submitted["target"] = feat.get("common_target", "CPEG Office")
        field_sources["submitted_to.target"] = "history_default"

    # contact number
    if predicted_input.get("contact_number"):
        field_sources["contact_number"] = "llm"
    else:
        predicted_input["contact_number"] = feat.get("common_contact_number", "")
        field_sources["contact_number"] = "history_stable" if predicted_input["contact_number"] else "missing"

    # supervisor
    if predicted_input.get("supervisor_advisor_faculty"):
        field_sources["supervisor_advisor_faculty"] = "llm"
    else:
        predicted_input["supervisor_advisor_faculty"] = feat.get("common_supervisor", "")
        field_sources["supervisor_advisor_faculty"] = "history_default" if predicted_input["supervisor_advisor_faculty"] else "missing"

    # expense detail
    detail = predicted_input.setdefault("expense_detail", {})

    # expense_group
    if detail.get("expense_group"):
        field_sources["expense_detail.expense_group"] = "llm"
    else:
        detail["expense_group"] = feat.get("common_expense_group", "")
        field_sources["expense_detail.expense_group"] = "history_default" if detail["expense_group"] else "missing"

    # business_purpose: preserve blank if missing
    if detail.get("business_purpose"):
        field_sources["expense_detail.business_purpose"] = "llm"
    else:
        detail["business_purpose"] = ""
        field_sources["expense_detail.business_purpose"] = "missing"

    # expense_description: preserve blank if missing
    if detail.get("expense_description"):
        field_sources["expense_detail.expense_description"] = "llm"
    else:
        detail["expense_description"] = ""
        field_sources["expense_detail.expense_description"] = "missing"

    # currency
    raw_currency = detail.get("currency")

    if raw_currency:
        detail["currency"] = str(raw_currency).upper()
        field_sources["expense_detail.currency"] = "llm"
    else:
        detail["currency"] = feat.get("common_currency", "HKD")
        field_sources["expense_detail.currency"] = (
            "history_stable" if detail["currency"] == "HKD" else "history_default"
        )

    # book_rate
    if detail["currency"] == "HKD":
        detail["book_rate"] = 1.0
        field_sources["expense_detail.book_rate"] = "rule"
    else:
        parsed_book_rate = safe_float_or_none(detail.get("book_rate"))

        if parsed_book_rate is None:
            detail["book_rate"] = None
            field_sources["expense_detail.book_rate"] = "missing"
        else:
            detail["book_rate"] = parsed_book_rate
            field_sources["expense_detail.book_rate"] = "llm"

    # amount: preserve None if missing
    raw_amount = detail.get("amount")
    parsed_amount = safe_float_or_none(raw_amount)

    if parsed_amount is None:
        detail["amount"] = None
        field_sources["expense_detail.amount"] = "missing"
    else:
        detail["amount"] = parsed_amount
        field_sources["expense_detail.amount"] = "llm"

    # equivalent_hkd_amount
    if detail.get("amount") is None or detail.get("book_rate") is None:
        detail["equivalent_hkd_amount"] = None
        field_sources["expense_detail.equivalent_hkd_amount"] = "missing"
    else:
        detail["equivalent_hkd_amount"] = round(
            detail["amount"] * detail["book_rate"],
            2
        )
        field_sources["expense_detail.equivalent_hkd_amount"] = "rule"

    # attach_receipt
    if "attach_receipt" in detail and detail.get("attach_receipt") is not None:
        detail["attach_receipt"] = bool(detail.get("attach_receipt"))
        field_sources["expense_detail.attach_receipt"] = "llm"
    else:
        receipt_ratio = float(feat.get("receipt_ratio", 0.8))
        detail["attach_receipt"] = True if receipt_ratio >= 0.5 else False
        field_sources["expense_detail.attach_receipt"] = "history_default"

    # declare_if_no_receipt
    if detail["attach_receipt"] is True:
        detail["declare_if_no_receipt"] = ""
        field_sources["expense_detail.declare_if_no_receipt"] = "rule"
    else:
        if detail.get("declare_if_no_receipt"):
            field_sources["expense_detail.declare_if_no_receipt"] = "llm"
        else:
            detail["declare_if_no_receipt"] = (
                "Receipt unavailable; details provided for verification."
            )
            field_sources["expense_detail.declare_if_no_receipt"] = "rule"

    return {
        "normalized_prediction": json.dumps(predicted_input, ensure_ascii=False),
        "normalized_llm_confidence": json.dumps(llm_field_confidence, ensure_ascii=False),
        "field_sources": json.dumps(field_sources, ensure_ascii=False),
        "explanations": json.dumps(explanations, ensure_ascii=False)
    }