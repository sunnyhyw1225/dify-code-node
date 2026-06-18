import json


def main(
    fixed_identity,
    predicted_input,
    field_scores,
    overall_score,
    display_mode,
    explanations,
    field_sources,
    missing_fields=None,
    required_user_input_reason=None,
    receipt_extraction=None,
):
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

    def safe_cell(value):
        if value is None:
            return ""
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        return text.replace("\n", " ").replace("\r", " ").replace("|", "\\|").strip()

    identity = parse_json_maybe(fixed_identity, {})
    pred = parse_json_maybe(predicted_input, {})
    scores = parse_json_maybe(field_scores, {})
    modes = parse_json_maybe(display_mode, {})
    expl = parse_json_maybe(explanations, [])
    sources = parse_json_maybe(field_sources, {})
    missing = parse_json_maybe(missing_fields, [])
    reasons = parse_json_maybe(required_user_input_reason, {})
    receipt = parse_json_maybe(receipt_extraction, {})

    expense = pred.get("expense_detail", {})
    submitted = pred.get("submitted_to", {})

    predicted_rows = [
        ("Submitted To Type", submitted.get("type")),
        ("Submitted To Target", submitted.get("target")),
        ("Contact Number", pred.get("contact_number")),
        ("Supervisor / Advisor / Faculty", pred.get("supervisor_advisor_faculty")),
        ("Expense Group", expense.get("expense_group")),
        ("Business Purpose", expense.get("business_purpose")),
        ("Expense Description", expense.get("expense_description")),
        ("Currency", expense.get("currency")),
        ("Amount", expense.get("amount")),
        ("Book Rate", expense.get("book_rate")),
        ("Equivalent HKD Amount", expense.get("equivalent_hkd_amount")),
        ("Attach Receipt", expense.get("attach_receipt")),
        ("Declaration If No Receipt", expense.get("declare_if_no_receipt")),
    ]

    predicted_table_lines = ["| Field | Predicted Value |", "|---|---|"]
    for field, value in predicted_rows:
        predicted_table_lines.append(f"| {field} | {safe_cell(value)} |")

    confidence_table_lines = [
        "| Field | Score | Display Mode | Source |",
        "|---|---:|---|---|",
    ]
    preferred_order = [
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

    for field in preferred_order:
        score = scores.get(field, "")
        try:
            score_display = f"{float(score):.4f}"
        except (TypeError, ValueError):
            score_display = safe_cell(score)
        confidence_table_lines.append(
            f"| {safe_cell(field)} | {score_display} | {safe_cell(modes.get(field))} | {safe_cell(sources.get(field))} |"
        )

    missing_table_lines = ["| Missing Field | Reason |", "|---|---|"]
    for field in missing if isinstance(missing, list) else []:
        missing_table_lines.append(
            f"| {safe_cell(field)} | {safe_cell(reasons.get(field))} |"
        )
    if len(missing_table_lines) == 2:
        missing_table_lines.append("| None | |")

    if isinstance(expl, list):
        explanation_text = "\n".join(f"- {safe_cell(item)}" for item in expl) if expl else "- None"
    else:
        explanation_text = safe_cell(expl)

    try:
        overall_score_display = f"{float(overall_score):.4f}"
    except (TypeError, ValueError):
        overall_score_display = safe_cell(overall_score)

    return {
        "status": "success" if pred else "empty",
        "pretty_fixed_identity": json.dumps(identity, ensure_ascii=False, indent=2),
        "pretty_receipt_extraction": json.dumps(receipt, ensure_ascii=False, indent=2),
        "pretty_predicted_table": "\n".join(predicted_table_lines),
        "pretty_confidence_table": "\n".join(confidence_table_lines),
        "pretty_missing_fields_table": "\n".join(missing_table_lines),
        "pretty_explanations": explanation_text,
        "pretty_predicted_json": json.dumps(pred, ensure_ascii=False, indent=2),
        "pretty_field_scores_json": json.dumps(scores, ensure_ascii=False, indent=2),
        "pretty_display_mode_json": json.dumps(modes, ensure_ascii=False, indent=2),
        "pretty_field_sources_json": json.dumps(sources, ensure_ascii=False, indent=2),
        "pretty_missing_fields_json": json.dumps(missing, ensure_ascii=False, indent=2),
        "pretty_required_user_input_reason_json": json.dumps(
            reasons,
            ensure_ascii=False,
            indent=2,
        ),
        "pretty_overall_score": overall_score_display,
    }
