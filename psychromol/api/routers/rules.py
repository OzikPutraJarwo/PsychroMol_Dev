from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ...defaults import DEFAULT_RULES
from ...rules import EQUIPMENT, SEVERITIES, validate_conditions
from ..deps import RepositoryDep
from ..schemas import RuleIn

router = APIRouter(prefix="/rules", tags=["rules"])

def _check(payload: RuleIn) -> list[dict[str, Any]]:
    conditions = [
        {k: v for k, v in item.model_dump().items() if v is not None}
        for item in payload.conditions
    ]
    problems = validate_conditions(conditions)
    if payload.severity not in SEVERITIES:
        problems.append(f"severity must be one of {', '.join(SEVERITIES)}")
    if payload.requires_equipment and payload.requires_equipment not in EQUIPMENT:
        problems.append(f"unknown equipment {payload.requires_equipment!r}")
    if problems:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems)
        )
    return conditions

@router.get("")
def list_rules(repository: RepositoryDep) -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in repository.list_rules()]

@router.post("", status_code=status.HTTP_201_CREATED)
def create_rule(payload: RuleIn, repository: RepositoryDep) -> dict[str, Any]:
    conditions = _check(payload)
    rule = repository.create_rule(
        name=payload.name,
        conditions=conditions,
        severity=payload.severity,
        recommendation=payload.recommendation,
        requires_equipment=payload.requires_equipment,
        priority=payload.priority,
        enabled=payload.enabled,
    )
    return rule.to_dict()

@router.put("/{rule_id}")
def update_rule(
    rule_id: int, payload: RuleIn, repository: RepositoryDep
) -> dict[str, Any]:
    conditions = _check(payload)
    rule = repository.update_rule(
        rule_id,
        name=payload.name,
        conditions=conditions,
        severity=payload.severity,
        recommendation=payload.recommendation,
        requires_equipment=payload.requires_equipment,
        priority=payload.priority,
        enabled=payload.enabled,
    )
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no rule {rule_id}")
    return rule.to_dict()

@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, repository: RepositoryDep) -> None:
    if not repository.delete_rule(rule_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no rule {rule_id}")

@router.post("/reset")
def reset_rules(repository: RepositoryDep) -> list[dict[str, Any]]:
    created = repository.replace_rules(DEFAULT_RULES)
    return [rule.to_dict() for rule in created]
