#!/usr/bin/env python3
"""Schema + lint checks for data/role_taxonomy.json governance."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "data" / "role_taxonomy.json"
SCHEMA_PATH = ROOT / "data" / "role_taxonomy.schema.json"

REQUIRED_TOP_LEVEL_KEYS = {"version", "created", "description", "roles"}
REQUIRED_ROLE_KEYS = {
    "role_id",
    "role_name",
    "onet_code",
    "category",
    "description",
    "required_skills",
    "preferred_skills",
    "barrier_conditions",
    "expected_signals",
    "motivation_attributes",
    "bls_data",
}
GENERIC_REQUIRED_SKILLS = {
    "Communication",
    "Critical Thinking",
    "Project Management",
    "Stakeholder Management",
    "Cross-Functional Leadership",
    "Strategic Planning",
    "Data Analysis",
    "Leadership",
    "Problem Solving",
    "Teamwork",
    "Change Management",
}
GENERIC_BARRIER_PATTERNS = [
    re.compile(r"^no experience$", re.IGNORECASE),
    re.compile(r"^poor communication skills$", re.IGNORECASE),
    re.compile(r"^lacks leadership$", re.IGNORECASE),
]
TESTABLE_SIGNAL_KEYWORDS = (
    "evidence",
    "track record",
    "prior",
    "experience",
    "portfolio",
    "published",
    "proficiency",
    "certification",
    "coursework",
    "performance",
    "wins",
    "demonstrated",
    "familiarity",
    "interest",
    "comfort",
    "strong",
    "exposure",
    "record",
    "knowledge",
    "understanding",
    "narrative",
    "applied",
    "background",
    "leadership",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def check_schema_shape(taxonomy: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(schema, dict) or "$defs" not in schema:
        errors.append(f"{SCHEMA_PATH} must contain a JSON schema object with $defs.")

    missing_top_level = REQUIRED_TOP_LEVEL_KEYS - set(taxonomy.keys())
    if missing_top_level:
        errors.append(f"Missing top-level keys: {sorted(missing_top_level)}")

    roles = taxonomy.get("roles")
    if not isinstance(roles, list) or not roles:
        errors.append("roles must be a non-empty array.")
        return errors

    for idx, role in enumerate(roles):
        if not isinstance(role, dict):
            errors.append(f"roles[{idx}] must be an object.")
            continue
        missing_role_keys = REQUIRED_ROLE_KEYS - set(role.keys())
        if missing_role_keys:
            errors.append(f"{role.get('role_id', f'roles[{idx}]')} missing keys: {sorted(missing_role_keys)}")

    return errors


def has_domain_distinguishing_required_skill(role: dict[str, Any]) -> bool:
    required_skills = role.get("required_skills", [])
    return any(skill not in GENERIC_REQUIRED_SKILLS for skill in required_skills)


def has_domain_distinguishing_signal(role: dict[str, Any]) -> bool:
    role_context = f"{role.get('role_name', '')} {role.get('category', '')}".lower()
    context_tokens = {token for token in re.split(r"[^a-z]+", role_context) if len(token) >= 4}
    signals = [s.lower() for s in role.get("expected_signals", [])]
    return any(any(token in signal for token in context_tokens) for signal in signals)


def barrier_conditions_are_non_generic(role: dict[str, Any]) -> bool:
    barriers = role.get("barrier_conditions", [])
    for barrier in barriers:
        if len(barrier.split()) < 4:
            return False
        if any(pattern.match(barrier.strip()) for pattern in GENERIC_BARRIER_PATTERNS):
            return False
    return True


def expected_signals_are_testable(role: dict[str, Any]) -> bool:
    signals = [s.lower() for s in role.get("expected_signals", [])]
    return all(any(keyword in signal for keyword in TESTABLE_SIGNAL_KEYWORDS) for signal in signals)


def lint_roles(taxonomy: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for role in taxonomy.get("roles", []):
        role_id = role.get("role_id", "unknown-role")

        if not role.get("required_skills"):
            errors.append(f"{role_id}: required_skills must be non-empty.")

        if not role.get("barrier_conditions"):
            errors.append(f"{role_id}: barrier_conditions must be non-empty.")

        if not role.get("expected_signals"):
            errors.append(f"{role_id}: expected_signals must be non-empty.")

        if not (
            has_domain_distinguishing_required_skill(role)
            or has_domain_distinguishing_signal(role)
        ):
            errors.append(
                f"{role_id}: include at least one domain-distinguishing required skill or expected signal."
            )

        if not barrier_conditions_are_non_generic(role):
            errors.append(
                f"{role_id}: barrier_conditions must be specific and non-generic (>= 4 words, no template-only lines)."
            )

        if not expected_signals_are_testable(role):
            errors.append(
                f"{role_id}: expected_signals must be testable against profile evidence (experience, portfolio, track record, etc.)."
            )

    return errors


def main() -> int:
    taxonomy = load_json(TAXONOMY_PATH)
    schema = load_json(SCHEMA_PATH)

    errors = check_schema_shape(taxonomy, schema)
    errors.extend(lint_roles(taxonomy))

    if errors:
        print("Role taxonomy validation failed:")
        for err in errors:
            print(f" - {err}")
        return 1

    print("Role taxonomy validation passed (schema shape + governance lint checks).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
