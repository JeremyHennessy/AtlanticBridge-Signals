"""Interpretation limits for CanadaBuys evidence; no source collection or correction."""
HISTORY_RESTRUCTURING_URL = "https://donnees-data.tpsgc-pwgsc.gc.ca/ba2/ac-cb/COsoutien-CHsupport-eng.html"
AMOUNT_STATUS = "WITHHELD_UNRECONCILED_NOTICE_AMOUNTS"
AMOUNT_WARNING = (
    "Published notice values are not automatically incremental spending or payments. "
    "An amendment may restate an existing contract value or be administrative. "
    "Reconcile the specific contract, revisions and amount semantics before aggregating; "
    "do not sum raw notice or history rows."
)
HISTORY_WARNING = (
    "The March-April 2026 CanadaBuys contract-history restructuring corrected repeated "
    "amounts and dates and removed certain administrative, placeholder-supplier and "
    "call-up records. Contract history is separate from this product's award-notice "
    "CSV; that notice does not establish that the award-notice feed was affected. "
    "Record the dataset/version before comparisons. A removed history row alone "
    "does not establish cancellation, a negative event or reduced spending."
)


def amount_policy() -> dict[str, str]:
    return {
        "amount_aggregation_status": AMOUNT_STATUS,
        "amount_aggregation_reason": AMOUNT_WARNING,
        "source_history_notice_url": HISTORY_RESTRUCTURING_URL,
        "source_history_notice_scope": "CANADABUYS_CONTRACT_HISTORY_NOT_AWARD_NOTICE_FEED",
        "source_history_warning": HISTORY_WARNING,
    }


def notice_quality() -> dict[str, str]:
    return {
        "amount_interpretation": "AS_PUBLISHED_NOTICE_VALUE_NOT_NEW_SPENDING",
        "amount_warning": AMOUNT_WARNING,
        "evidence_role": "COMMERCIAL_RESEARCH_SIGNAL",
    }
