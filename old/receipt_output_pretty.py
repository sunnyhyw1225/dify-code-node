import json


def main(
    fixed_identity,
    predicted_input=None,
    field_scores=None,
    overall_score=None,
    display_mode=None,
    explanations=None,
    field_sources=None,
    missing_fields=None,
    required_user_input_reason=None,
    receipt_extraction=None,
    scored_results=None,
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

    def build_section(result, index):
        pred = parse_json_maybe(result.get("predicted_input", {}), {})
        scores = parse_json_maybe(result.get("field_scores", {}), {})
        modes = parse_json_maybe(result.get("display_mode", {}), {})
        sources = parse_json_maybe(result.get("field_sources", {}), {})
        missing = parse_json_maybe(result.get("missing_fields", []), [])
        reasons = parse_json_maybe(result.get("required_user_input_reason", {}), {})
        expl = parse_json_maybe(result.get("explanations", []), [])

        expense = pred.get("expense_detail", {})
        submitted = pred.get("submitted_to", {})
        receipt_group_id = result.get("receipt_group_id")
        source_file_indices = parse_json_maybe(result.get("source_file_indices", []), [])
        same_receipt = result.get("same_receipt")

        predicted_rows = [
            ("Receipt Group ID", receipt_group_id),
            ("Source File Indices", source_file_indices),
            ("Same Receipt Group", same_receipt),
            ("Submitted To Type", submitted.get("type")),
            ("Submitted To Target", submitted.get("target")),
            ("Contact Number", pred.get("contact_number")),
            ("Supervisor / Advisor / Faculty", pred.get("supervisor_advisor_faculty")),
            ("Date From", pred.get("date_from")),
            ("Date End", pred.get("date_end")),
            ("Expense Group", expense.get("expense_group")),
            ("Business Purpose", expense.get("business_purpose")),
            ("Expense Description", expense.get("expense_description")),
            ("Currency", expense.get("currency")),
            ("Amount", expense.get("amount")),
            ("Attach Receipt", expense.get("attach_receipt")),
            ("Declaration If No Receipt", expense.get("declare_if_no_receipt")),
        ]

        predicted_table_lines = [f"Receipt {index}", "| Field | Predicted Value |", "|---|---|"]
        for field, value in predicted_rows:
            predicted_table_lines.append(f"| {field} | {safe_cell(value)} |")

        preferred_order = [
            "submitted_to.type",
            "submitted_to.target",
            "contact_number",
            "supervisor_advisor_faculty",
            "date_from",
            "date_end",
            "expense_detail.expense_group",
            "expense_detail.business_purpose",
            "expense_detail.expense_description",
            "expense_detail.currency",
            "expense_detail.amount",
            "expense_detail.attach_receipt",
            "expense_detail.declare_if_no_receipt",
        ]
        confidence_table_lines = [
            f"Receipt {index}",
            "| Field | Score | Display Mode | Source |",
            "|---|---:|---|---|",
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

        missing_table_lines = [f"Receipt {index}", "| Missing Field | Reason |", "|---|---|"]
        for field in missing if isinstance(missing, list) else []:
            missing_table_lines.append(
                f"| {safe_cell(field)} | {safe_cell(reasons.get(field))} |"
            )
        if len(missing_table_lines) == 3:
            missing_table_lines.append("| None | |")

        if isinstance(expl, list):
            explanation_text = "\n".join(f"- {safe_cell(item)}" for item in expl) if expl else "- None"
        else:
            explanation_text = safe_cell(expl)

        return {
            "predicted_table": "\n".join(predicted_table_lines),
            "confidence_table": "\n".join(confidence_table_lines),
            "missing_table": "\n".join(missing_table_lines),
            "explanations": f"Receipt {index}\n{explanation_text}",
            "full_section": "\n\n".join(
                [
                    f"## Receipt {index}",
                    section_header_line("Predicted Form Input"),
                    "\n".join(predicted_table_lines[1:]),
                    section_header_line("Field-Level Confidence"),
                    "\n".join(confidence_table_lines[1:]),
                    section_header_line("Missing Fields"),
                    "\n".join(missing_table_lines[1:]),
                    section_header_line("Explanation"),
                    explanation_text,
                ]
            ),
        }

    def section_header_line(title):
        return f"### {title}"

    identity = parse_json_maybe(fixed_identity, {})
    receipt = parse_json_maybe(receipt_extraction, {})
    parsed_scored_results = parse_json_maybe(scored_results, None)

    if isinstance(parsed_scored_results, list) and parsed_scored_results:
        predicted_sections = []
        confidence_sections = []
        missing_sections = []
        explanation_sections = []

        for index, result in enumerate(parsed_scored_results, start=1):
            section = build_section(result, index)
            predicted_sections.append(section["predicted_table"])
            confidence_sections.append(section["confidence_table"])
            missing_sections.append(section["missing_table"])
            explanation_sections.append(section["explanations"])

        receipt_sections = []
        for index, result in enumerate(parsed_scored_results, start=1):
            receipt_sections.append(build_section(result, index)["full_section"])

        return {
            "status": "success",
            "pretty_fixed_identity": json.dumps(identity, ensure_ascii=False, indent=2),
            "pretty_receipt_extraction": json.dumps(receipt, ensure_ascii=False, indent=2),
            "pretty_predicted_table": "\n\n".join(predicted_sections),
            "pretty_confidence_table": "\n\n".join(confidence_sections),
            "pretty_missing_fields_table": "\n\n".join(missing_sections),
            "pretty_explanations": "\n\n".join(explanation_sections),
            "pretty_predicted_json": json.dumps(parsed_scored_results, ensure_ascii=False, indent=2),
            "pretty_field_scores_json": json.dumps(parsed_scored_results, ensure_ascii=False, indent=2),
            "pretty_display_mode_json": json.dumps(parsed_scored_results, ensure_ascii=False, indent=2),
            "pretty_field_sources_json": json.dumps(parsed_scored_results, ensure_ascii=False, indent=2),
            "pretty_missing_fields_json": json.dumps(parsed_scored_results, ensure_ascii=False, indent=2),
            "pretty_required_input_json": json.dumps(parsed_scored_results, ensure_ascii=False, indent=2),
            "pretty_overall_score": safe_cell(overall_score),
            "pretty_receipt_sections": "\n\n---\n\n".join(receipt_sections),
        }

    pred = parse_json_maybe(predicted_input, {})
    scores = parse_json_maybe(field_scores, {})
    modes = parse_json_maybe(display_mode, {})
    expl = parse_json_maybe(explanations, [])
    sources = parse_json_maybe(field_sources, {})
    missing = parse_json_maybe(missing_fields, [])
    reasons = parse_json_maybe(required_user_input_reason, {})

    expense = pred.get("expense_detail", {})
    submitted = pred.get("submitted_to", {})

    predicted_rows = [
        ("Submitted To Type", submitted.get("type")),
        ("Submitted To Target", submitted.get("target")),
        ("Contact Number", pred.get("contact_number")),
        ("Supervisor / Advisor / Faculty", pred.get("supervisor_advisor_faculty")),
        ("Date From", pred.get("date_from")),
        ("Date End", pred.get("date_end")),
        ("Expense Group", expense.get("expense_group")),
        ("Business Purpose", expense.get("business_purpose")),
        ("Expense Description", expense.get("expense_description")),
        ("Currency", expense.get("currency")),
        ("Amount", expense.get("amount")),
        ("Attach Receipt", expense.get("attach_receipt")),
        ("Declaration If No Receipt", expense.get("declare_if_no_receipt")),
    ]

    predicted_table_lines = ["| Field | Predicted Value |", "|---|---|"]
    for field, value in predicted_rows:
        predicted_table_lines.append(f"| {field} | {safe_cell(value)} |")

    preferred_order = [
        "submitted_to.type",
        "submitted_to.target",
        "contact_number",
        "supervisor_advisor_faculty",
        "date_from",
        "date_end",
        "expense_detail.expense_group",
        "expense_detail.business_purpose",
        "expense_detail.expense_description",
        "expense_detail.currency",
        "expense_detail.amount",
        "expense_detail.attach_receipt",
        "expense_detail.declare_if_no_receipt",
    ]
    confidence_table_lines = ["| Field | Score | Display Mode | Source |", "|---|---:|---|---|"]
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
        missing_table_lines.append(f"| {safe_cell(field)} | {safe_cell(reasons.get(field))} |")
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
        "pretty_required_input_json": json.dumps(reasons, ensure_ascii=False, indent=2),
        "pretty_overall_score": overall_score_display,
        "pretty_receipt_sections": "\n\n".join(
            [
                "## Receipt 1",
                "### Predicted Form Input",
                "\n".join(predicted_table_lines),
                "### Field-Level Confidence",
                "\n".join(confidence_table_lines),
                "### Missing Fields",
                "\n".join(missing_table_lines),
                "### Explanation",
                explanation_text,
            ]
        ),
    }
