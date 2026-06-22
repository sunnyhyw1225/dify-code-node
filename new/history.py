import json
from collections import Counter

def get_nested_value(data, field_path):
    keys = field_path.split(".")
    value = data

    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]

    return value


def most_frequent_field(history_data, field_path):
    values = []

    for record in history_data:
        value = get_nested_value(record, field_path)

        if value not in [None, ""]:
            values.append(value)

    if not values:
        return None

    return Counter(values).most_common(1)[0][0]


def main(history_json: str) -> dict:
    try:
        history_data = json.loads(history_json)

        submitted_to_type = most_frequent_field(
            history_data,
            "submitted_to.type"
        )

        submitted_to_target = most_frequent_field(
            history_data,
            "submitted_to.target"
        )

        contact_number = most_frequent_field(
            history_data,
            "contact_number"
        )

        supervisor_advisor_faculty = most_frequent_field(
            history_data,
            "supervisor_advisor_faculty"
        )

        result = {
            "submitted_to": {
                "type": submitted_to_type or "code node did not find a consistent type",
                "target": submitted_to_target or "code node did not find a consistent target"
            },
            "contact_number": contact_number,
            "supervisor_advisor_faculty": supervisor_advisor_faculty
        }

        return {
            "history_defaults_json": json.dumps(result, ensure_ascii=False)
        }

    except Exception as e:
        return {
            "history_defaults_json": json.dumps({
                "error": str(e)
            }, ensure_ascii=False)
        }