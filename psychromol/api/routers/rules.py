from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from ..deps import ProfileDep, RepositoryDep
from ..schemas import RuleIn

router = APIRouter(tags=["rules"])


@router.get("/profiles/{profile_id}/rules")
def list_rules(profile: ProfileDep, repository: RepositoryDep) -> list[dict[str, Any]]:
    return [rule.to_dict() for rule in repository.list_rules(profile.id)]


@router.put("/profiles/{profile_id}/rules")
def replace_rules(
    profile: ProfileDep, payload: list[RuleIn], repository: RepositoryDep
) -> list[dict[str, Any]]:
    rules = repository.replace_rules(profile, [rule.model_dump() for rule in payload])
    return [rule.to_dict() for rule in rules]


@router.post("/profiles/{profile_id}/rules", status_code=status.HTTP_201_CREATED)
def create_rule(profile: ProfileDep, payload: RuleIn, repository: RepositoryDep) -> dict[str, Any]:
    return repository.create_rule(profile.id, **payload.model_dump()).to_dict()


def _rule(rule_id: int, repository: RepositoryDep):
    rule = repository.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no rule {rule_id}")
    return rule


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, payload: RuleIn, repository: RepositoryDep) -> dict[str, Any]:
    return repository.update_rule(_rule(rule_id, repository), **payload.model_dump()).to_dict()


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, repository: RepositoryDep) -> None:
    repository.delete_rule(_rule(rule_id, repository))
