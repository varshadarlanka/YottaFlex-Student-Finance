from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional


@dataclass(frozen=True)
class ScholarshipRule:
    code: str
    name: str
    scholarship_type: str
    description: str
    applicable_fee_types: tuple[str, ...]
    max_amount_paise: Optional[int] = None
    percentage_discount: Optional[float] = None
    is_renewable: bool = False
    effective_from: str = "2024-01-01"
    effective_to: Optional[str] = None
    allowed_program_levels: tuple[str, ...] = ()
    allowed_departments: tuple[str, ...] = ()
    allowed_genders: tuple[str, ...] = ()
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    min_year_of_study: Optional[int] = None
    max_year_of_study: Optional[int] = None
    min_score: Optional[int] = None


@dataclass
class FinancePolicy:
    invoice_due_days: int = 30
    late_fee_enabled: bool = False
    late_fee_rate_bps: int = 0
    late_fee_grace_days: int = 0
    scholarship_rules: list[ScholarshipRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.scholarship_rules:
            self.scholarship_rules = self.default_scholarship_rules()

    @staticmethod
    def default_scholarship_rules() -> list[ScholarshipRule]:
        return [
            ScholarshipRule(
                code="MERIT-ACADEMIC",
                name="Merit Academic Scholarship",
                scholarship_type="Merit",
                description=(
                    "High-scoring students in UG and PG programmes receive a partial "
                    "tuition waiver based on a deterministic academic score."
                ),
                applicable_fee_types=("Tuition",),
                max_amount_paise=8_000_000,
                percentage_discount=35.0,
                is_renewable=True,
                allowed_program_levels=("UG", "PG"),
                min_year_of_study=1,
                max_year_of_study=3,
                min_score=88,
            ),
            ScholarshipRule(
                code="ACCESS-SUPPORT",
                name="Access Support Grant",
                scholarship_type="Need-based",
                description=(
                    "Students from non-metro cities receive support against tuition and "
                    "development fees."
                ),
                applicable_fee_types=("Tuition", "Development"),
                max_amount_paise=3_000_000,
                percentage_discount=20.0,
                allowed_program_levels=("UG", "PG", "Diploma", "Certificate"),
                min_year_of_study=1,
                max_year_of_study=4,
                min_score=52,
            ),
            ScholarshipRule(
                code="GOV-WOMEN-STEM",
                name="Government Women in STEM Scholarship",
                scholarship_type="Government",
                description=(
                    "Female students in Engineering and Computing programmes receive a "
                    "government-backed tuition subsidy."
                ),
                applicable_fee_types=("Tuition", "Lab"),
                max_amount_paise=5_500_000,
                percentage_discount=30.0,
                is_renewable=True,
                allowed_program_levels=("UG", "PG", "Diploma", "Certificate"),
                allowed_departments=("Engineering", "Computing"),
                allowed_genders=("F",),
                min_year_of_study=1,
                max_year_of_study=4,
                min_score=60,
            ),
            ScholarshipRule(
                code="SPORTS-EXCELLENCE",
                name="Sports Excellence Grant",
                scholarship_type="Sports",
                description=(
                    "Students with a strong extracurricular score receive a fixed grant "
                    "against sports, tuition, and development fees."
                ),
                applicable_fee_types=("Sports", "Tuition", "Development"),
                max_amount_paise=1_800_000,
                percentage_discount=15.0,
                allowed_program_levels=("UG", "PG", "Diploma"),
                max_age=25,
                min_score=78,
            ),
            ScholarshipRule(
                code="RESEARCH-GRANT",
                name="Research Progress Grant",
                scholarship_type="Special",
                description=(
                    "PG and PhD students in research-oriented programmes receive support "
                    "for research and library-related fees."
                ),
                applicable_fee_types=("Research", "Library", "Tuition"),
                max_amount_paise=6_500_000,
                percentage_discount=25.0,
                is_renewable=True,
                allowed_program_levels=("PG", "PhD"),
                allowed_departments=("Research", "Sciences", "Engineering", "Computing"),
                min_year_of_study=1,
                max_year_of_study=3,
                min_score=70,
            ),
        ]

    def get_rule(self, scholarship_code: str) -> ScholarshipRule:
        for rule in self.scholarship_rules:
            if rule.code == scholarship_code:
                return rule
        raise KeyError(f"Unknown scholarship rule: {scholarship_code}")

    @staticmethod
    def normalize_payment_status(value: str) -> str:
        aliases = {
            "successful": "cleared",
            "succeeded": "cleared",
            "cleared": "cleared",
            "pending": "pending",
            "failed": "failed",
            "reversed": "reversed",
            "refunded": "refunded",
        }
        key = value.strip().lower().replace("-", "_")
        if key not in aliases:
            raise ValueError(f"Unsupported payment status: {value}")
        return aliases[key]

    @staticmethod
    def display_payment_status(value: str) -> str:
        return "successful" if value == "cleared" else value

    @staticmethod
    def normalize_payment_method(value: str) -> str:
        aliases = {
            "cash": "Cash",
            "upi": "UPI",
            "bank_transfer": "NEFT",
            "bank transfer": "NEFT",
            "netbanking": "NetBanking",
            "net_banking": "NetBanking",
            "card": "CardDebit",
            "card_debit": "CardDebit",
            "card_credit": "CardCredit",
            "neft": "NEFT",
            "rtgs": "RTGS",
            "other": "Other",
            "chequedd": "ChequeDD",
            "cheque": "ChequeDD",
        }
        key = value.strip().lower().replace("-", "_")
        if key not in aliases:
            raise ValueError(f"Unsupported payment method: {value}")
        return aliases[key]

    @staticmethod
    def display_payment_method(value: str) -> str:
        mapping = {
            "NetBanking": "bank_transfer",
            "NEFT": "bank_transfer",
            "RTGS": "bank_transfer",
            "CardDebit": "card",
            "CardCredit": "card",
            "UPI": "upi",
            "Other": "other",
            "Cash": "cash",
            "ChequeDD": "other",
        }
        return mapping.get(value, value.lower())

    def calculate_due_date(self, issue_date: str) -> str:
        return (date.fromisoformat(issue_date) + timedelta(days=self.invoice_due_days)).isoformat()

    def calculate_award_amount(self, rule: ScholarshipRule, eligible_fee_amount: int) -> int:
        if eligible_fee_amount <= 0:
            return 0

        award = eligible_fee_amount
        if rule.percentage_discount is not None:
            award = int(eligible_fee_amount * (rule.percentage_discount / 100.0))
        if rule.max_amount_paise is not None:
            award = min(award, rule.max_amount_paise)
        return max(0, min(award, eligible_fee_amount))

    def applicable_fee_types(self, fee_types: Iterable[str], rule: ScholarshipRule) -> set[str]:
        allowed = set(rule.applicable_fee_types)
        return {fee_type for fee_type in fee_types if fee_type in allowed}
