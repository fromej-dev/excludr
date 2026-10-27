"""Plans and prices: the single source of truth for limits and the pricing page.

Projects without a pass share a small free allowance per owner account. A review
pass is a one-off payment for one project, tiered by the number of articles the
AI agent screens at the full-text stage (the main driver of AI cost).
"""

from dataclasses import dataclass

CURRENCY = "eur"
PASS_DURATION_DAYS = 365

# Free allowance, shared by all projects of an owner that have no pass.
FREE_FULLTEXT_LIMIT = 50
# Title/abstract AI screening is cheap; it is only capped as fair use.
FREE_TITLE_ABSTRACT_LIMIT = 500
PASS_TITLE_ABSTRACT_LIMIT = 10_000

CUSTOM_TIER = "custom"  # admin grants with an arbitrary limit


@dataclass(frozen=True)
class Tier:
    code: str
    label: str
    fulltext_limit: int
    price_cents: int


TIERS: dict[str, Tier] = {
    t.code: t
    for t in (
        Tier("pass_250", "Review pass, up to 250 full texts", 250, 4900),
        Tier("pass_1000", "Review pass, up to 1,000 full texts", 1000, 12900),
    )
}
