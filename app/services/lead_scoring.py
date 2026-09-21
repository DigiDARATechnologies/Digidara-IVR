"""Non-persisted score preview used only by the manual calculator."""


def calculate_preview_score(
    interested: bool,
    budget: bool,
    decision_maker: bool,
    callback_requested: bool
):

    score = 0

    if interested:
        score += 40

    if budget:
        score += 20

    if decision_maker:
        score += 20

    if callback_requested:
        score += 20

    if score >= 70:
        status = "HOT_LEAD"
    elif score >= 40:
        status = "WARM_LEAD"
    else:
        status = "COLD_LEAD"

    return {
        "lead_score": score,
        "status": status,
        "source": "manual_preview",
        "persisted": False,
    }


# Backward-compatible import for API clients; never use this during call finalization.
calculate_lead_score = calculate_preview_score
