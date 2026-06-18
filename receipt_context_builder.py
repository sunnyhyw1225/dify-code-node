import datetime
import json


def main(
    requestor,
    department,
    email,
    student_id,
    upload_files=None,
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

    def normalize_upload_files(value):
        raw_files = parse_json_maybe(value, value)

        if raw_files is None:
            return []
        if isinstance(raw_files, dict):
            raw_files = [raw_files]
        if not isinstance(raw_files, list):
            return [{"name": str(raw_files), "type": "", "size": None}]

        files = []
        for item in raw_files:
            if isinstance(item, dict):
                files.append(
                    {
                        "name": item.get("name") or item.get("filename") or item.get("title") or "",
                        "type": item.get("mime_type") or item.get("type") or item.get("extension") or "",
                        "size": item.get("size"),
                        "url": item.get("url") or item.get("download_url") or "",
                    }
                )
            else:
                files.append({"name": str(item), "type": "", "size": None, "url": ""})
        return files

    def load_settings_inline(settings_payload, currency_values, expense_group_values):
        data = parse_json_maybe(settings_payload, {})
        if not isinstance(data, dict):
            data = {}

        currencies = [
            value.upper()
            for value in clean_string_list(
                currency_values if currency_values is not None else data.get("currencies", [])
            )
        ]
        expense_groups = clean_string_list(
            expense_group_values if expense_group_values is not None else data.get("expense_groups", [])
        )

        return {
            "currencies": currencies,
            "expense_groups": expense_groups,
        }

    settings = load_settings_inline(settings_json, currencies, expense_groups)
    fixed_identity = {
        "requestor": requestor,
        "email": email,
        "department": department,
        "student_id": str(student_id) if student_id is not None else "",
    }
    file_summary = normalize_upload_files(upload_files)

    context_obj = {
        "timestamp": datetime.datetime.now(
            tz=datetime.timezone(datetime.timedelta(hours=8))
        ).isoformat(),
        "identity": fixed_identity,
        "upload_summary": {
            "file_count": len(file_summary),
            "files": file_summary,
        },
        "allowed_form_options": {
            "currencies": settings["currencies"],
            "expense_groups": settings["expense_groups"],
        },
    }

    return {
        "fixed_identity": fixed_identity,
        "fixed_identity_for_llm": json.dumps(fixed_identity, ensure_ascii=False),
        "allowed_form_options": json.dumps(
            {
                "currencies": settings["currencies"],
                "expense_groups": settings["expense_groups"],
            },
            ensure_ascii=False,
        ),
        "enriched_context": json.dumps(context_obj, ensure_ascii=False),
        "upload_file_summary": json.dumps(file_summary, ensure_ascii=False),
    }
