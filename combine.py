import json


def parse_json(value, fallback):
    if value is None:
        return fallback

    if isinstance(value, (dict, list)):
        return value

    if isinstance(value, str):
        value = value.strip()

        if value.startswith("```"):
            value = value.strip("`")
            value = value.replace("json\n", "", 1).replace("JSON\n", "", 1).strip()

        try:
            return json.loads(value)
        except Exception:
            return fallback

    return fallback


def clean(value, default=""):
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    return value


def get_first_receipt(gemini_data):
    if isinstance(gemini_data, dict):
        receipts = gemini_data.get("receipts")
        if isinstance(receipts, list) and receipts:
            return receipts[0]
        return gemini_data

    if isinstance(gemini_data, list) and gemini_data:
        return gemini_data[0]

    return {}


def get_llm_expense_detail(llm_data):
    try:
        return (
            llm_data
            .get("results", [{}])[0]
            .get("predicted_input", {})
            .get("expense_detail", {})
        )
    except Exception:
        return {}


def get_llm_missing_fields(llm_data):
    try:
        return llm_data.get("results", [{}])[0].get("missing_fields", [])
    except Exception:
        return []


def extract_file_refs(receipt_file):
    """
    Converts Dify file array into filename/URL list.

    Supports:
    - list of file objects
    - JSON string list
    - single file object
    - plain string
    """

    files = parse_json(receipt_file, receipt_file)

    if files in [None, ""]:
        return []

    if isinstance(files, str):
        return [files]

    if isinstance(files, dict):
        ref = (
            files.get("url")
            or files.get("remote_url")
            or files.get("signed_url")
            or files.get("name")
            or files.get("filename")
            or files.get("file_name")
        )
        return [ref] if ref else []

    if isinstance(files, list):
        refs = []

        for file_obj in files:
            if isinstance(file_obj, str):
                refs.append(file_obj)
            elif isinstance(file_obj, dict):
                ref = (
                    file_obj.get("url")
                    or file_obj.get("remote_url")
                    or file_obj.get("signed_url")
                    or file_obj.get("name")
                    or file_obj.get("filename")
                    or file_obj.get("file_name")
                )

                if ref:
                    refs.append(ref)

        return refs

    return []


def main(
    llm_claim_json: str,
    gemini_ocr_json: str,
    history_json: str,
    receipt_file
) -> dict:

    llm_data = parse_json(llm_claim_json, {"results": []})
    gemini_data = parse_json(gemini_ocr_json, {})
    history = parse_json(history_json, {})

    receipt = get_first_receipt(gemini_data)
    llm_expense = get_llm_expense_detail(llm_data)

    file_refs = extract_file_refs(receipt_file)

    submitted_to = history.get("submitted_to", {})

    date_start = clean(
        receipt.get("transaction_date_start")
        or receipt.get("transaction_date")
        or receipt.get("date")
    )

    date_end = clean(
        receipt.get("transaction_date_end")
        or receipt.get("date_end")
    )

    if date_start and not date_end:
        date_end = date_start

    currency = clean(receipt.get("currency"))

    amount = clean(
        receipt.get("amount_paid")
        or receipt.get("total")
        or receipt.get("grand_total")
    )

    expense_description = clean(llm_expense.get("expense_description"))
    expense_group = clean(llm_expense.get("expense_group"))
    business_purpose = clean(llm_expense.get("business_purpose"))

    missing_fields = get_llm_missing_fields(llm_data)

    if not isinstance(missing_fields, list):
        missing_fields = []

    required_checks = {
        "transaction_date_start": date_start,
        "currency": currency,
        "amount": amount,
        "expense_description": expense_description,
        "expense_group": expense_group,
        "business_purpose": business_purpose
    }

    for field, value in required_checks.items():
        if value == "" and field not in missing_fields:
            missing_fields.append(field)

    final_output = {
        "requestor": clean(history.get("requestor") or history.get("fixed_identity", {}).get("requestor")),
        "department": clean(history.get("department") or history.get("fixed_identity", {}).get("department")),
        "email": clean(history.get("email") or history.get("fixed_identity", {}).get("email")),
        "student_id": clean(history.get("student_id") or history.get("fixed_identity", {}).get("student_id")),
        "contact_number": clean(history.get("contact_number")),
        "supervisor_advisor_faculty": clean(history.get("supervisor_advisor_faculty")),
        "submitted_to": {
            "type": clean(submitted_to.get("type"), "null"),
            "target": clean(submitted_to.get("target"), "null")
        },
        "receipts": [
            {
                "transaction_date_start": date_start,
                "transaction_date_end": date_end,
                "expense_description": expense_description,
                "currency": currency,
                "amount": amount,
                "expense_group": expense_group,
                "business_purpose": business_purpose,
                "attach_receipt": file_refs,
                "missing_fields": missing_fields
            }
        ]
    }

    return {
        "final_claim_json": json.dumps(final_output, ensure_ascii=False)
    }