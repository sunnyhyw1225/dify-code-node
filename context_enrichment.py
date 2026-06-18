import json
import datetime

def main(intent, referrer, context_note, session_id, user_id):
    fixed_identity = {
        "requestor": "Sunny Hon",
        "email": "abc@connect.ust.hk",
        "department": "CPEG",
        "student_id": "20000001",
    }

    context_obj = {
        "timestamp": datetime.datetime.now(
            tz=datetime.timezone(datetime.timedelta(hours=8))
        ).isoformat(),
        "intent": intent,
        "referrer": referrer or "direct",
        "context_note": context_note or "",
        "session_id": session_id,
        "user_id": user_id,
        "identity": fixed_identity,
    }

    enriched_context = json.dumps(context_obj, ensure_ascii=False)
    return {
        "fixed_identity": fixed_identity,
        "enriched_context": enriched_context,
    }