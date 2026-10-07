"""
dvalidate - 声明式校验引擎
configs/validation_rules.yaml 驱动。
校验结果：pass / warn / block
block → quarantine 行级隔离
warn → 入库但标记
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class RuleSeverity(Enum):
    WARN = "warn"
    BLOCK = "block"


@dataclass
class RuleViolation:
    rule_name: str
    severity: RuleSeverity
    message: str
    row_key: str = ""
    expected: Any = None
    got: Any = None


@dataclass
class ValidationResult:
    passed: bool
    violations: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def has_blocks(self):
        return any(v.severity == RuleSeverity.BLOCK for v in self.violations)


class ValidationRule:
    """Base class for validation rules."""

    def __init__(self, name: str, severity: RuleSeverity = RuleSeverity.BLOCK):
        self.name = name
        self.severity = severity

    def check(self, row: dict, context: dict = None) -> Optional[RuleViolation]:
        raise NotImplementedError


class OHLCConsistencyRule(ValidationRule):
    """high >= max(open, close) >= min(open, close) >= low > 0"""

    def __init__(self):
        super().__init__("ohlc_consistency", RuleSeverity.BLOCK)

    def check(self, row: dict, context: dict = None) -> Optional[RuleViolation]:
        o, h, l, c = row.get("open"), row.get("high"), row.get("low"), row.get("close")
        if any(v is None for v in [h, l, c]):
            return None  # not_null handles this

        if o is not None and h < max(o, c):
            return RuleViolation(self.name, self.severity,
                                 f"high({h}) < max(open({o}), close({c}))",
                                 expected=f">= {max(o, c)}", got=h)
        if l > min(o or l, c):
            return RuleViolation(self.name, self.severity,
                                 f"low({l}) > min(open({o}), close({c}))",
                                 expected=f"<= {min(o or l, c)}", got=l)
        if l <= 0:
            return RuleViolation(self.name, self.severity,
                                 f"low({l}) <= 0", expected="> 0", got=l)
        return None


class MagnitudeRule(ValidationRule):
    """0.01 < close < 1e6; 0 <= volume < 1e11; 0 <= amount < 1e13"""

    def __init__(self):
        super().__init__("magnitude", RuleSeverity.BLOCK)

    def check(self, row: dict, context: dict = None) -> Optional[RuleViolation]:
        close = row.get("close")
        if close is not None:
            if not (0.01 < close < 1e6):
                return RuleViolation(self.name, self.severity,
                                     f"close({close}) out of range (0.01, 1e6)",
                                     expected="(0.01, 1e6)", got=close)

        vol = row.get("volume") or row.get("vol")
        if vol is not None:
            if not (0 <= vol < 1e11):
                return RuleViolation(self.name, self.severity,
                                     f"volume({vol}) out of range [0, 1e11)",
                                     expected="[0, 1e11)", got=vol)

        amount = row.get("amount")
        if amount is not None:
            if not (0 <= amount < 1e13):
                return RuleViolation(self.name, self.severity,
                                     f"amount({amount}) out of range [0, 1e13)",
                                     expected="[0, 1e13)", got=amount)
        return None


class NotNullRule(ValidationRule):
    """PK columns and close must be non-null."""

    def __init__(self, required_fields: list = None):
        super().__init__("not_null", RuleSeverity.BLOCK)
        self.required_fields = required_fields or ["close"]

    def check(self, row: dict, context: dict = None) -> Optional[RuleViolation]:
        for f in self.required_fields:
            if row.get(f) is None:
                return RuleViolation(self.name, self.severity,
                                     f"Required field '{f}' is null",
                                     expected="not null", got=None)
        return None


class PctConsistencyRule(ValidationRule):
    """|pct - (close/prev_close - 1) * 100| <= 0.02"""

    def __init__(self):
        super().__init__("pct_consistency", RuleSeverity.BLOCK)

    def check(self, row: dict, context: dict = None) -> Optional[RuleViolation]:
        pct = row.get("pct")
        prev_close = (context or {}).get("prev_close")
        close = row.get("close")

        if pct is None or prev_close is None or close is None:
            return None

        expected_pct = (close / prev_close - 1) * 100
        diff = abs(pct - expected_pct)
        if diff > 0.02:
            return RuleViolation(self.name, self.severity,
                                 f"pct({pct}) deviates from expected({expected_pct:.2f}) by {diff:.4f}",
                                 expected=expected_pct, got=pct)
        return None


class SoftWarnRule(ValidationRule):
    """turnover_rate > 100% → warn"""

    def __init__(self):
        super().__init__("soft_warn", RuleSeverity.WARN)

    def check(self, row: dict, context: dict = None) -> Optional[RuleViolation]:
        tr = row.get("turnover_rate")
        if tr is not None and tr > 100:
            return RuleViolation(self.name, self.severity,
                                 f"turnover_rate({tr}) > 100%",
                                 expected="<= 100", got=tr)
        return None


# Default rules registry
DEFAULT_RULES = {
    "ohlc_consistency": OHLCConsistencyRule,
    "magnitude": MagnitudeRule,
    "not_null": NotNullRule,
    "pct_consistency": PctConsistencyRule,
    "soft_warn": SoftWarnRule,
}


class ValidationEngine:
    """
    声明式校验引擎。
    逐行执行规则集，返回 block/warn 结果。
    """

    def __init__(self, config_path: str = None, rules: list = None):
        self.rules = []
        if rules:
            self.rules = rules
        else:
            # Load defaults
            self.rules = [cls() for cls in DEFAULT_RULES.values()]

        if config_path and Path(config_path).exists():
            self._load_config(config_path)

    def _load_config(self, config_path: str):
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        # Extend with config-defined rules (future enhancement)
        logger.info(f"Loaded validation config from {config_path}")

    def validate_row(self, row: dict, context: dict = None) -> ValidationResult:
        violations = []
        for rule in self.rules:
            v = rule.check(row, context)
            if v:
                violations.append(v)

        blocks = [v for v in violations if v.severity == RuleSeverity.BLOCK]
        warns = [v for v in violations if v.severity == RuleSeverity.WARN]

        return ValidationResult(
            passed=len(blocks) == 0,
            violations=violations,
            warnings=warns
        )

    def validate_batch(self, rows: list, context: dict = None) -> tuple:
        """Returns (passed_rows, blocked_rows, warned_rows)"""
        passed = []
        blocked = []
        warned = []

        for row in rows:
            result = self.validate_row(row, context)
            row_key = self._extract_row_key(row)

            if result.has_blocks:
                blocked.append({
                    "row": row,
                    "row_key": row_key,
                    "failed_rules": [
                        f"{v.rule_name}:expect={v.expected},got={v.got}"
                        for v in result.violations if v.severity == RuleSeverity.BLOCK
                    ]
                })
            elif result.warnings:
                warned.append({
                    "row": row,
                    "row_key": row_key,
                    "warnings": [v.message for v in result.warnings]
                })
                passed.append(row)  # warn still passes
            else:
                passed.append(row)

        return passed, blocked, warned

    def _extract_row_key(self, row: dict) -> str:
        """Extract a row key for quarantine tracking."""
        parts = []
        for k in ["date", "ts", "code", "contract_id"]:
            if k in row:
                parts.append(str(row[k]))
        return "|".join(parts) if parts else "unknown"
