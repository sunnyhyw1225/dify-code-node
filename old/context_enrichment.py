import json
import datetime

from settings_loader import load_settings

def main(requestor, department, email, student_id):
    fixed_identity = {
        "requestor": requestor,
        "email": email,
        "department": department,
        "student_id": student_id,
    }
    form_settings = load_settings()

    context_obj = {
        "timestamp": datetime.datetime.now(
            tz=datetime.timezone(datetime.timedelta(hours=8))
        ).isoformat(),
        "identity": fixed_identity,
        "allowed_form_options": {
            "currencies": form_settings["currencies"],
            "expense_groups": form_settings["expense_groups"],
        },
    }

    enriched_context = json.dumps(context_obj, ensure_ascii=False)
    return {
        "fixed_identity": fixed_identity,
        "fixed_identity_for_llm": json.dumps(fixed_identity, ensure_ascii=False),
        "allowed_form_options": json.dumps(
            {
                "currencies": form_settings["currencies"],
                "expense_groups": form_settings["expense_groups"],
            },
            ensure_ascii=False,
        ),
        "enriched_context": enriched_context,
    }
