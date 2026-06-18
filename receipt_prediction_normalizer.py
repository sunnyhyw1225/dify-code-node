import json
import re


def main(
    llm_raw_output,
    history_features=None,
    receipt_extraction=None,
    receipt_raw_text=None,
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

    def strip_fence(text):
        text = str(text or "").strip()
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return text.strip()

    def extract_first_json_object(text):
        start = text.find("{")
        if start < 0:
            raise ValueError("No JSON object found in LLM output.")
        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]

        raise ValueError("Incomplete JSON object in LLM output.")

    def safe_float_or_none(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def parse_bool_or_none(value):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "yes", "y", "1"}:
            return True
        if text in {"false", "no", "n", "0"}:
            return False
        return None

    def normalize_text_or_none(value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

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

    def get_history_default(features, field):
        stable_defaults = features.get("stable_defaults", {})
        entry = stable_defaults.get(field, {})
        if isinstance(entry, dict) and entry.get("use_as_default") is True:
            return entry.get("value")
        return None

    def get_default_source(features, field):
        return "history_default" if get_history_default(features, field) is not None else "rule"

    def normalize_missing_fields(value):
        items = parse_json_maybe(value, value)
        if items is None:
            return []
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    raw = strip_fence(llm_raw_output)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = json.loads(extract_first_json_object(raw))

    feat = parse_json_maybe(history_features, {})
    receipt = parse_json_maybe(receipt_extraction, {})
    raw_receipt_text = normalize_text_or_none(receipt_raw_text)

    predicted_input = obj.get("predicted_input", {})
    if not isinstance(predicted_input, dict):
        predicted_input = {}

    llm_field_confidence = parse_json_maybe(obj.get("llm_field_confidence", {}), {})
    if not isinstance(llm_field_confidence, dict):
        llm_field_confidence = {}

    missing_fields = normalize_missing_fields(obj.get("missing_fields", []))
    required_user_input_reason = parse_json_maybe(
        obj.get("required_user_input_reason", {}),
        {},
    )
    if not isinstance(required_user_input_reason, dict):
        required_user_input_reason = {}

    explanations = parse_json_maybe(obj.get("explanations", []), [])
    if not isinstance(explanations, list):
        explanations = [str(explanations)]
    explanations = [str(item).strip() for item in explanations if str(item).strip()][:3]

    field_sources = {}

    submitted = predicted_input.setdefault("submitted_to", {})
    if not isinstance(submitted, dict):
        submitted = {}
        predicted_input["submitted_to"] = submitted

    detail = predicted_input.setdefault("expense_detail", {})
    if not isinstance(detail, dict):
        detail = {}
        predicted_input["expense_detail"] = detail

    submitted_type = normalize_text_or_none(submitted.get("type"))
    if submitted_type not in {"Department", "Specific Endorser"}:
        submitted_type = get_history_default(feat, "submitted_to.type") or "Department"
        field_sources["submitted_to.type"] = get_default_source(feat, "submitted_to.type")
    else:
        field_sources["submitted_to.type"] = "llm"
    submitted["type"] = submitted_type

    submitted_target = normalize_text_or_none(submitted.get("target"))
    if submitted_target is None:
        submitted_target = get_history_default(feat, "submitted_to.target") or "CPEG Office"
        field_sources["submitted_to.target"] = get_default_source(feat, "submitted_to.target")
    else:
        field_sources["submitted_to.target"] = "llm"
    submitted["target"] = submitted_target

    contact_number = normalize_text_or_none(predicted_input.get("contact_number"))
    if contact_number is None:
        contact_number = normalize_text_or_none(get_history_default(feat, "contact_number"))
        field_sources["contact_number"] = "history_stable" if contact_number else "missing"
    else:
        field_sources["contact_number"] = "llm"
    predicted_input["contact_number"] = contact_number

    supervisor = normalize_text_or_none(predicted_input.get("supervisor_advisor_faculty"))
    if supervisor is None:
        supervisor = normalize_text_or_none(
            get_history_default(feat, "supervisor_advisor_faculty")
        )
        field_sources["supervisor_advisor_faculty"] = (
            "history_default" if supervisor else "missing"
        )
    else:
        field_sources["supervisor_advisor_faculty"] = "llm"
    predicted_input["supervisor_advisor_faculty"] = supervisor

    normalized_group = normalize_expense_group(detail.get("expense_group"))
    if normalized_group is None:
        normalized_group = None
        field_sources["expense_detail.expense_group"] = "missing"
    else:
        field_sources["expense_detail.expense_group"] = "context_inferred"
    detail["expense_group"] = normalized_group

    business_purpose = normalize_text_or_none(detail.get("business_purpose"))
    detail["business_purpose"] = business_purpose
    field_sources["expense_detail.business_purpose"] = (
        "context_inferred" if business_purpose else "missing"
    )

    expense_description = normalize_text_or_none(detail.get("expense_description"))
    if expense_description is None:
        expense_description = normalize_text_or_none(receipt.get("merchant_name"))
        field_sources["expense_detail.expense_description"] = (
            "receipt_explicit" if expense_description else "missing"
        )
    else:
        field_sources["expense_detail.expense_description"] = "receipt_explicit"
    detail["expense_description"] = expense_description

    currency = normalize_currency(detail.get("currency"))
    if currency is None:
        currency = normalize_currency(receipt.get("currency"))
        field_sources["expense_detail.currency"] = (
            "receipt_explicit" if currency else "missing"
        )
    else:
        field_sources["expense_detail.currency"] = "receipt_explicit"
    detail["currency"] = currency

    amount = safe_float_or_none(detail.get("amount"))
    if amount is None:
        amount = safe_float_or_none(receipt.get("total_amount"))
        field_sources["expense_detail.amount"] = "receipt_explicit" if amount is not None else "missing"
    else:
        field_sources["expense_detail.amount"] = "receipt_explicit"
    detail["amount"] = amount

    book_rate = safe_float_or_none(detail.get("book_rate"))
    if currency == "HKD":
        book_rate = 1.0
        field_sources["expense_detail.book_rate"] = "rule"
    elif book_rate is None:
        book_rate = safe_float_or_none(receipt.get("exchange_rate"))
        field_sources["expense_detail.book_rate"] = (
            "receipt_explicit" if book_rate is not None else "missing"
        )
    else:
        field_sources["expense_detail.book_rate"] = "llm"
    detail["book_rate"] = book_rate

    if amount is not None and book_rate is not None:
        detail["equivalent_hkd_amount"] = round(amount * book_rate, 2)
        field_sources["expense_detail.equivalent_hkd_amount"] = "rule"
    else:
        detail["equivalent_hkd_amount"] = None
        field_sources["expense_detail.equivalent_hkd_amount"] = "missing"

    attach_receipt = parse_bool_or_none(detail.get("attach_receipt"))
    receipt_evidence_present = bool(receipt) or bool(raw_receipt_text)
    if attach_receipt is None:
        attach_receipt = True if receipt_evidence_present else None
        field_sources["expense_detail.attach_receipt"] = (
            "receipt_explicit" if attach_receipt is True else "missing"
        )
    else:
        field_sources["expense_detail.attach_receipt"] = (
            "receipt_explicit" if attach_receipt is True else "llm"
        )
    detail["attach_receipt"] = attach_receipt

    declare_if_no_receipt = normalize_text_or_none(detail.get("declare_if_no_receipt"))
    if attach_receipt is True:
        declare_if_no_receipt = ""
        field_sources["expense_detail.declare_if_no_receipt"] = "rule"
    elif attach_receipt is False:
        field_sources["expense_detail.declare_if_no_receipt"] = (
            "llm" if declare_if_no_receipt else "missing"
        )
    else:
        declare_if_no_receipt = None
        field_sources["expense_detail.declare_if_no_receipt"] = "missing"
    detail["declare_if_no_receipt"] = declare_if_no_receipt

    default_missing_fields = []
    if detail["amount"] is None:
        default_missing_fields.append("expense_detail.amount")
    if detail["currency"] is None:
        default_missing_fields.append("expense_detail.currency")
    if detail["expense_group"] is None:
        default_missing_fields.append("expense_detail.expense_group")
    if detail["business_purpose"] is None:
        default_missing_fields.append("expense_detail.business_purpose")

    merged_missing = []
    seen = set()
    for field in missing_fields + default_missing_fields:
        if field not in seen:
            merged_missing.append(field)
            seen.add(field)

    if "expense_detail.amount" in merged_missing and "expense_detail.amount" not in required_user_input_reason:
        required_user_input_reason["expense_detail.amount"] = (
            "The receipt does not show a single clear final amount."
        )
    if (
        "expense_detail.business_purpose" in merged_missing
        and "expense_detail.business_purpose" not in required_user_input_reason
    ):
        required_user_input_reason["expense_detail.business_purpose"] = (
            "The receipt does not explain the academic or business purpose."
        )
    if (
        "expense_detail.currency" in merged_missing
        and "expense_detail.currency" not in required_user_input_reason
    ):
        required_user_input_reason["expense_detail.currency"] = (
            "The receipt currency is missing or ambiguous."
        )
    if (
        "expense_detail.expense_group" in merged_missing
        and "expense_detail.expense_group" not in required_user_input_reason
    ):
        required_user_input_reason["expense_detail.expense_group"] = (
            "The receipt does not map clearly to one configured expense group."
        )

    return {
        "normalized_prediction": json.dumps(predicted_input, ensure_ascii=False),
        "normalized_llm_confidence": json.dumps(llm_field_confidence, ensure_ascii=False),
        "field_sources": json.dumps(field_sources, ensure_ascii=False),
        "explanations": json.dumps(explanations, ensure_ascii=False),
        "missing_fields": json.dumps(merged_missing, ensure_ascii=False),
        "required_user_input_reason": json.dumps(
            required_user_input_reason,
            ensure_ascii=False,
        ),
    }
