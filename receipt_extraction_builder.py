import json


def main(
    ocr_or_vision_output=None,
    upload_files=None,
    receipt_raw_text=None,
    settings_json=None,
    currencies=None,
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

    def safe_float_or_none(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def first_non_empty(obj, keys):
        if not isinstance(obj, dict):
            return None
        for key in keys:
            value = obj.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    def normalize_upload_files(value):
        raw_files = parse_json_maybe(value, value)
        if raw_files is None:
            return []
        if isinstance(raw_files, dict):
            raw_files = [raw_files]
        if not isinstance(raw_files, list):
            return [{"name": str(raw_files), "type": "", "size": None}]

        normalized = []
        for item in raw_files:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "name": item.get("name") or item.get("filename") or item.get("title") or "",
                        "type": item.get("mime_type") or item.get("type") or item.get("extension") or "",
                        "size": item.get("size"),
                    }
                )
            else:
                normalized.append({"name": str(item), "type": "", "size": None})
        return normalized

    def load_currencies(settings_payload, currency_values):
        data = parse_json_maybe(settings_payload, {})
        if not isinstance(data, dict):
            data = {}

        return {
            value.upper()
            for value in clean_string_list(
                currency_values if currency_values is not None else data.get("currencies", [])
            )
        }

    def normalize_currency(value):
        allowed_currencies = load_currencies(settings_json, currencies)
        if value is None:
            return None

        text = str(value).strip().upper()
        if not text:
            return None

        return text if text in allowed_currencies else None

    def normalize_line_items(value):
        if value is None:
            return []
        if isinstance(value, str):
            return [{"description": value}]
        if not isinstance(value, list):
            return []

        items = []
        for item in value:
            if isinstance(item, dict):
                items.append(
                    {
                        "description": item.get("description") or item.get("name") or item.get("item") or "",
                        "quantity": item.get("quantity"),
                        "unit_price": safe_float_or_none(
                            item.get("unit_price") or item.get("price")
                        ),
                        "amount": safe_float_or_none(
                            item.get("amount") or item.get("total")
                        ),
                    }
                )
            else:
                items.append({"description": str(item)})
        return items

    def normalize_currency_value(obj):
        value = first_non_empty(
            obj,
            [
                "currency",
                "currency_code",
                "transaction_currency",
                "original_currency",
            ],
        )
        if value is None and isinstance(obj, dict):
            symbol = obj.get("currency_symbol") or obj.get("symbol")
            symbol_map = {
                "$": None,
                "HK$": "HKD",
                "US$": "USD",
                "A$": "AUD",
                "C$": "CAD",
                "S$": "SGD",
                "MOP$": "MOP",
                "GBP": "GBP",
                "EUR": "EUR",
                "JPY": "JPY",
                "RMB": "CNY",
                "CNY": "CNY",
                "HKD": "HKD",
            }
            value = symbol_map.get(str(symbol).strip(), symbol)
        return normalize_currency(value)

    parsed_output = parse_json_maybe(ocr_or_vision_output, None)

    if isinstance(parsed_output, list):
        parsed_output = parsed_output[0] if parsed_output else {}
    if parsed_output is None:
        parsed_output = {}
    if not isinstance(parsed_output, dict):
        parsed_output = {"raw_text": str(ocr_or_vision_output or "")}

    raw_text = receipt_raw_text
    if raw_text in (None, ""):
        raw_text = first_non_empty(
            parsed_output,
            ["raw_text", "ocr_text", "text", "content", "markdown", "plain_text"],
        ) or ""

    merchant_name = first_non_empty(
        parsed_output,
        ["merchant_name", "merchant", "vendor", "payee", "store_name", "seller"],
    )
    transaction_date = first_non_empty(
        parsed_output,
        ["transaction_date", "receipt_date", "date", "purchase_date"],
    )
    total_amount = safe_float_or_none(
        first_non_empty(
            parsed_output,
            [
                "total_amount",
                "grand_total",
                "final_total",
                "net_amount_paid",
                "settled_amount",
                "amount",
                "total",
            ],
        )
    )
    subtotal_amount = safe_float_or_none(
        first_non_empty(parsed_output, ["subtotal", "sub_total"])
    )
    tax_amount = safe_float_or_none(
        first_non_empty(parsed_output, ["tax_amount", "tax", "vat", "gst"])
    )
    tip_amount = safe_float_or_none(
        first_non_empty(parsed_output, ["tip_amount", "tip", "service_charge"])
    )
    discount_amount = safe_float_or_none(
        first_non_empty(parsed_output, ["discount_amount", "discount"])
    )
    exchange_rate = safe_float_or_none(
        first_non_empty(parsed_output, ["exchange_rate", "book_rate", "fx_rate"])
    )

    normalized_extraction = {
        "merchant_name": merchant_name,
        "transaction_date": transaction_date,
        "currency": normalize_currency_value(parsed_output),
        "total_amount": total_amount,
        "subtotal_amount": subtotal_amount,
        "tax_amount": tax_amount,
        "tip_amount": tip_amount,
        "discount_amount": discount_amount,
        "exchange_rate": exchange_rate,
        "payment_method": first_non_empty(
            parsed_output,
            ["payment_method", "payment_type", "method"],
        ),
        "card_last4": first_non_empty(
            parsed_output,
            ["card_last4", "last4", "masked_card_number"],
        ),
        "invoice_number": first_non_empty(
            parsed_output,
            ["invoice_number", "receipt_number", "invoice_id", "reference_number"],
        ),
        "line_items": normalize_line_items(
            first_non_empty(parsed_output, ["line_items", "items", "products"])
        ),
        "ocr_confidence": safe_float_or_none(
            first_non_empty(parsed_output, ["ocr_confidence", "confidence"])
        ),
        "source_model": first_non_empty(
            parsed_output,
            ["source_model", "model", "provider"],
        ),
        "file_summary": normalize_upload_files(upload_files),
    }

    return {
        "receipt_extraction": json.dumps(normalized_extraction, ensure_ascii=False),
        "receipt_raw_text": str(raw_text or ""),
        "receipt_file_summary": json.dumps(
            normalized_extraction["file_summary"],
            ensure_ascii=False,
        ),
    }
