import json
from collections import Counter, defaultdict

from settings_loader import load_settings, normalize_currency, normalize_expense_group

def main(historical_json_text: str):
    def parse_json_maybe(value, default):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return default

    def safe_float(value):
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def percentile(vals, p):
        if not vals:
            return 0.0
        vals = sorted(vals)
        idx = int((len(vals) - 1) * p)
        return vals[idx]

    def amount_summary(vals):
        vals = sorted(vals)
        if not vals:
            return {
                "count": 0,
                "min": 0.0,
                "p25": 0.0,
                "median": 0.0,
                "p75": 0.0,
                "max": 0.0,
                "avg": 0.0
            }

        return {
            "count": len(vals),
            "min": round(vals[0], 2),
            "p25": round(percentile(vals, 0.25), 2),
            "median": round(percentile(vals, 0.5), 2),
            "p75": round(percentile(vals, 0.75), 2),
            "max": round(vals[-1], 2),
            "avg": round(sum(vals) / len(vals), 2)
        }

    def top_entry(counter, total):
        if not counter or total <= 0:
            return {
                "value": None,
                "count": 0,
                "ratio": 0.0,
                "reliability": "none",
                "use_as_default": False
            }

        value, count = counter.most_common(1)[0]
        ratio = count / total

        if ratio >= 0.85 and count >= 5:
            reliability = "high"
            use_as_default = True
        elif ratio >= 0.60 and count >= 3:
            reliability = "medium"
            use_as_default = True
        elif ratio >= 0.35 and count >= 2:
            reliability = "low"
            use_as_default = False
        else:
            reliability = "weak"
            use_as_default = False

        return {
            "value": value,
            "count": count,
            "ratio": round(ratio, 4),
            "reliability": reliability,
            "use_as_default": use_as_default
        }

    def counter_to_ranked_list(counter, total, limit=5):
        rows = []
        if total <= 0:
            return rows

        for value, count in counter.most_common(limit):
            rows.append({
                "value": value,
                "count": count,
                "ratio": round(count / total, 4)
            })
        return rows

    data = parse_json_maybe(historical_json_text, {})
    apps = data.get("applications", [])
    settings = load_settings()
    default_currency = settings["default_currency"] or "HKD"
    default_expense_group = settings["default_expense_group"] or "Others"

    submitted_type_counter = Counter()
    submitted_target_counter = Counter()
    submitted_pair_counter = Counter()
    contact_counter = Counter()
    supervisor_counter = Counter()
    currency_counter = Counter()
    expense_group_counter = Counter()
    receipt_counter = Counter()

    amounts = []
    amounts_by_group = defaultdict(list)
    receipt_true_by_group = Counter()
    total_by_group = Counter()

    supervisor_by_group = defaultdict(Counter)
    target_by_group = defaultdict(Counter)
    currency_by_group = defaultdict(Counter)

    valid_apps = 0

    for app in apps:
        if not isinstance(app, dict):
            continue

        detail = app.get("expense_detail", {})
        submitted = app.get("submitted_to", {})

        if not isinstance(detail, dict):
            detail = {}
        if not isinstance(submitted, dict):
            submitted = {}

        valid_apps += 1

        submitted_type = submitted.get("type") or "Unknown"
        submitted_target = submitted.get("target") or "Unknown"
        submitted_pair = f"{submitted_type}::{submitted_target}"

        contact = app.get("contact_number") or None
        supervisor = app.get("supervisor_advisor_faculty") or "Unknown"
        currency = normalize_currency(detail.get("currency")) or default_currency
        group = normalize_expense_group(detail.get("expense_group")) or default_expense_group
        receipt = detail.get("attach_receipt")

        submitted_type_counter[submitted_type] += 1
        submitted_target_counter[submitted_target] += 1
        submitted_pair_counter[submitted_pair] += 1

        if contact:
            contact_counter[contact] += 1

        supervisor_counter[supervisor] += 1
        currency_counter[currency] += 1
        expense_group_counter[group] += 1

        total_by_group[group] += 1
        supervisor_by_group[group][supervisor] += 1
        target_by_group[group][submitted_target] += 1
        currency_by_group[group][currency] += 1

        if receipt is True:
            receipt_counter["true"] += 1
            receipt_true_by_group[group] += 1
        elif receipt is False:
            receipt_counter["false"] += 1
        else:
            receipt_counter["unknown"] += 1

        amount = safe_float(detail.get("amount"))
        if amount is not None:
            amounts.append(amount)
            amounts_by_group[group].append(amount)

    amount_stats_by_group = {
        group: amount_summary(vals)
        for group, vals in amounts_by_group.items()
    }

    receipt_ratio_by_group = {
        group: round(receipt_true_by_group[group] / total_by_group[group], 4)
        for group in total_by_group
    }

    full_features = {
        "sample_size": len(apps),
        "valid_apps": valid_apps,

        "stable_defaults": {
            "submitted_to.type": top_entry(submitted_type_counter, valid_apps),
            "submitted_to.target": top_entry(submitted_target_counter, valid_apps),
            "submitted_to.pair": top_entry(submitted_pair_counter, valid_apps),
            "contact_number": top_entry(contact_counter, valid_apps),
            "supervisor_advisor_faculty": top_entry(supervisor_counter, valid_apps),
            "expense_detail.currency": top_entry(currency_counter, valid_apps),
            "expense_detail.expense_group": top_entry(expense_group_counter, valid_apps),
            "expense_detail.attach_receipt": top_entry(receipt_counter, valid_apps)
        },

        "ranked_patterns": {
            "submitted_to.type": counter_to_ranked_list(submitted_type_counter, valid_apps),
            "submitted_to.target": counter_to_ranked_list(submitted_target_counter, valid_apps),
            "contact_number": counter_to_ranked_list(contact_counter, valid_apps),
            "supervisor_advisor_faculty": counter_to_ranked_list(supervisor_counter, valid_apps),
            "expense_detail.currency": counter_to_ranked_list(currency_counter, valid_apps),
            "expense_detail.expense_group": counter_to_ranked_list(expense_group_counter, valid_apps),
            "expense_detail.attach_receipt": counter_to_ranked_list(receipt_counter, valid_apps)
        },

        "amount_stats": amount_summary(amounts),
        "amount_stats_by_expense_group": amount_stats_by_group,
        "receipt_ratio_by_expense_group": receipt_ratio_by_group,

        "conditional_patterns": {
            "common_supervisor_by_expense_group": {
                group: top_entry(counter, total_by_group[group])
                for group, counter in supervisor_by_group.items()
            },
            "common_target_by_expense_group": {
                group: top_entry(counter, total_by_group[group])
                for group, counter in target_by_group.items()
            },
            "common_currency_by_expense_group": {
                group: top_entry(counter, total_by_group[group])
                for group, counter in currency_by_group.items()
            }
        },

        "quality": {
            "small_sample": valid_apps < 10,
            "very_small_sample": valid_apps < 5,
            "amount_data_count": len(amounts),
            "expense_group_count": len(expense_group_counter)
        }
    }

    # Compact version for LLM.
    # This is intentionally smaller and more directive than full_features.
    history_profile_for_llm = {
        "sample_size": valid_apps,
        "allowed_values": {
            "currencies": settings["currencies"],
            "expense_groups": settings["expense_groups"],
        },
        "how_to_use_history": [
            "Use stable defaults only when current context does not provide a value.",
            "Do not use weak historical patterns as if they are facts.",
            "Do not fill event-specific fields from history alone unless explicitly allowed.",
            "Prefer current context over historical patterns when they conflict."
        ],
        "stable_defaults": full_features["stable_defaults"],
        "top_expense_groups": full_features["ranked_patterns"]["expense_detail.expense_group"],
        "amount_ranges_by_expense_group": amount_stats_by_group,
        "receipt_ratio_by_expense_group": receipt_ratio_by_group,
        "conditional_patterns": full_features["conditional_patterns"],
        "quality": full_features["quality"]
    }

    return {
        "history_features": json.dumps(full_features, ensure_ascii=False),
        "history_profile_for_llm": json.dumps(history_profile_for_llm, ensure_ascii=False)
    }
