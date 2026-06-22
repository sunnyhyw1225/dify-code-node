import json

def clean(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def main(
    requestor: str,
    department: str,
    email: str,
    student_id: str,
    submitted_to_type: str,
    submitted_to_target: str,
    contact_number: str,
    supervisor_advisor_faculty: str
) -> dict:

    submitted_type = clean(submitted_to_type)
    submitted_target = clean(submitted_to_target)

    history = {
        "fixed_identity": {
            "requestor": clean(requestor),
            "department": clean(department),
            "email": clean(email),
            "student_id": clean(student_id)
        },
        "submitted_to": {
            "type": submitted_type,
            "target": submitted_target
        },
        "contact_number": clean(contact_number),
        "supervisor_advisor_faculty": clean(supervisor_advisor_faculty)
    }

    return {
        "history_json": json.dumps(history, ensure_ascii=False)
    }