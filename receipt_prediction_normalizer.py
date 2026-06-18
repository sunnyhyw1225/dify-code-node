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

    def extract_first_json_value(text):
        object_start = text.find("{")
        array_start = text.find("[")
        if object_start < 0 and array_start < 0:
            raise ValueError("No JSON value found in LLM output.")
        if object_start < 0:
            start = array_start
        elif array_start < 0:
            start = object_start
        else:
            start = min(object_start, array_start)

        opening = text[start]
        closing = "}" if opening == "{" else "]"
        if opening not in {"{", "["}:
            raise ValueError("No JSON value found in LLM output.")

        if start < 0:
            raise ValueError("No JSON value found in LLM output.")
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
            elif char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]

        raise ValueError("Incomplete JSON value in LLM output.")

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

    def normalize_date_or_none(value):
        text = normalize_text_or_none(value)
        if text is None:
            return None
        return text

    def load_settings_inline(settings_payload, currency_values, expense_group_values):
        data = parse_json_maybe(settings_payload, {})
        if not isinstance(data, dict):
            data = {}

        allowed_currencies = {
            value.upper()
            for value in clean_string_list(
                currency_values if currency_values is not None else data.get("currencies", [])
            )
        }
        allowed_expense_groups = set(
            clean_string_list(
                expense_group_values
                if expense_group_values is not None
                else data.get("expense_groups", [])
            )
        )

        return {
            "currencies": allowed_currencies,
            "expense_groups": allowed_expense_groups,
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

    def normalize_source_file_indices(value):
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        result = []
        for item in value:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    def build_fallback_obj(message):
        return {
            "results": [
                {
                    "predicted_input": {},
                    "llm_field_confidence": {},
                    "missing_fields": [],
                    "required_user_input_reason": {},
                    "explanations": [message],
                }
            ]
        }

    def parse_llm_output(raw_output):
        raw_text = strip_fence(raw_output)
        if not raw_text:
            return build_fallback_obj("LLM output was empty."), True

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            try:
                extracted = extract_first_json_value(raw_text)
                parsed = json.loads(extracted)
            except (json.JSONDecodeError, ValueError):
                return build_fallback_obj("LLM output was not valid JSON."), True

        if isinstance(parsed, list):
            return {"results": parsed}, False
        if isinstance(parsed, dict):
            return parsed, False
        return build_fallback_obj("LLM output JSON was not an object."), True

    obj, used_fallback_obj = parse_llm_output(llm_raw_output)

    feat = parse_json_maybe(history_features, {})
    receipt = parse_json_maybe(receipt_extraction, {})
    raw_receipt_text = normalize_text_or_none(receipt_raw_text)

    def normalize_single_result(result_obj, fallback_group_index):
        result_obj = result_obj if isinstance(result_obj, dict) else {}

        predicted_input = result_obj.get("predicted_input", {})
        if not isinstance(predicted_input, dict):
            predicted_input = {}

        llm_field_confidence = parse_json_maybe(
            result_obj.get("llm_field_confidence", {}),
            {},
        )
        if not isinstance(llm_field_confidence, dict):
            llm_field_confidence = {}

        missing_fields = normalize_missing_fields(result_obj.get("missing_fields", []))
        required_user_input_reason = parse_json_maybe(
            result_obj.get("required_user_input_reason", {}),
            {},
        )
        if not isinstance(required_user_input_reason, dict):
            required_user_input_reason = {}

        explanations = parse_json_maybe(result_obj.get("explanations", []), [])
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
        detail.pop("book_rate", None)
        detail.pop("equivalent_hkd_amount", None)

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

        predicted_input["contact_number"] = None
        field_sources["contact_number"] = "missing"

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

        date_from = normalize_date_or_none(predicted_input.get("date_from"))
        if date_from is None:
            date_from = normalize_date_or_none(
                result_obj.get("date_from") or receipt.get("date_from") or receipt.get("transaction_date")
            )
            field_sources["date_from"] = "receipt_explicit" if date_from else "missing"
        else:
            field_sources["date_from"] = "receipt_explicit"
        predicted_input["date_from"] = date_from

        date_end = normalize_date_or_none(predicted_input.get("date_end"))
        if date_end is None:
            receipt_date_end = normalize_date_or_none(result_obj.get("date_end") or receipt.get("date_end"))
            if receipt_date_end is not None:
                date_end = receipt_date_end
                field_sources["date_end"] = "receipt_explicit"
            elif date_from is not None:
                date_end = date_from
                field_sources["date_end"] = "rule"
            else:
                field_sources["date_end"] = "missing"
        else:
            field_sources["date_end"] = "receipt_explicit"
        predicted_input["date_end"] = date_end

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
        if predicted_input["date_from"] is None:
            default_missing_fields.append("date_from")
        if predicted_input["date_end"] is None:
            default_missing_fields.append("date_end")
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
        if "date_from" in merged_missing and "date_from" not in required_user_input_reason:
            required_user_input_reason["date_from"] = (
                "The receipt does not show a clear start or transaction date."
            )
        if "date_end" in merged_missing and "date_end" not in required_user_input_reason:
            required_user_input_reason["date_end"] = (
                "The receipt does not show a clear end date."
            )
        if (
            "expense_detail.expense_group" in merged_missing
            and "expense_detail.expense_group" not in required_user_input_reason
        ):
            required_user_input_reason["expense_detail.expense_group"] = (
                "The receipt does not map clearly to one configured expense group."
            )

        receipt_group_id = normalize_text_or_none(result_obj.get("receipt_group_id"))
        if receipt_group_id is None:
            receipt_group_id = f"receipt_{fallback_group_index}"

        return {
            "receipt_group_id": receipt_group_id,
            "source_file_indices": normalize_source_file_indices(result_obj.get("source_file_indices")),
            "same_receipt": parse_bool_or_none(result_obj.get("same_receipt")),
            "predicted_input": predicted_input,
            "llm_field_confidence": llm_field_confidence,
            "field_sources": field_sources,
            "explanations": explanations,
            "missing_fields": merged_missing,
            "required_user_input_reason": required_user_input_reason,
        }

    raw_results = obj.get("results")
    if isinstance(raw_results, list) and raw_results:
        results = raw_results
    else:
        results = [obj]

    normalized_results = [
        normalize_single_result(result, index)
        for index, result in enumerate(results, start=1)
    ]

    first_result = normalized_results[0] if normalized_results else {
        "predicted_input": {},
        "llm_field_confidence": {},
        "field_sources": {},
        "explanations": [],
        "missing_fields": [],
        "required_user_input_reason": {},
    }

    if used_fallback_obj and not first_result["missing_fields"]:
        first_result["missing_fields"] = [
            "expense_detail.amount",
            "expense_detail.currency",
            "date_from",
            "date_end",
            "expense_detail.expense_group",
            "expense_detail.business_purpose",
        ]
        first_result["required_user_input_reason"] = {
            "expense_detail.amount": "The extraction model did not return usable JSON output.",
            "expense_detail.currency": "The extraction model did not return usable JSON output.",
            "date_from": "The extraction model did not return usable JSON output.",
            "date_end": "The extraction model did not return usable JSON output.",
            "expense_detail.expense_group": "The extraction model did not return usable JSON output.",
            "expense_detail.business_purpose": "The extraction model did not return usable JSON output.",
        }
        normalized_results[0] = first_result

    return {
        "normalized_results": json.dumps(normalized_results, ensure_ascii=False),
        "normalized_prediction": json.dumps(first_result["predicted_input"], ensure_ascii=False),
        "normalized_llm_confidence": json.dumps(first_result["llm_field_confidence"], ensure_ascii=False),
        "field_sources": json.dumps(first_result["field_sources"], ensure_ascii=False),
        "explanations": json.dumps(first_result["explanations"], ensure_ascii=False),
        "missing_fields": json.dumps(first_result["missing_fields"], ensure_ascii=False),
        "required_user_input_reason": json.dumps(
            first_result["required_user_input_reason"],
            ensure_ascii=False,
        ),
    }
