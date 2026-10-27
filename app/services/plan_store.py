import json
from typing import Any, List, Literal, TypedDict, cast

from app.services.etag import canonical_json
from app.services.redis import keys, redis


# shared types
# NOTE: the TS types carry an index signature ([k: string]: unknown); TypedDict
# cannot express that, but extra keys are tolerated at runtime (plain dicts).
class MemberCostShare(TypedDict):
    objectId: str
    objectType: Literal["membercostshare"]


class Service(TypedDict):
    objectId: str
    objectType: Literal["service"]


class PlanService(TypedDict):
    objectId: str
    objectType: Literal["planservice"]
    linkedService: Service
    planserviceCostShares: MemberCostShare


class Plan(TypedDict):
    objectId: str
    objectType: Literal["plan"]
    planCostShares: MemberCostShare
    linkedPlanServices: List[PlanService]


class KeyValue(TypedDict):
    key: str
    value: str


def _object_id(obj: Any) -> Any:
    # Equivalent of `obj?.objectId`
    if isinstance(obj, dict):
        return obj.get("objectId")
    return None


# Build all Redis key/value pairs for a plan and its children
def build_redis_writes_from_plan(plan: Plan) -> List[KeyValue]:
    results: List[KeyValue] = []

    # whole-plan document (for existing GET /plans, ETag, etc.)
    results.append({"key": keys.plan(plan["objectId"]), "value": canonical_json(plan)})

    # plan as its own key (for KV listing like in demo)
    results.append(
        {"key": keys.plan_object(plan["objectId"]), "value": canonical_json(plan)}
    )

    # planCostShares
    pcs = plan.get("planCostShares")
    if _object_id(pcs):
        results.append(
            {"key": keys.plan_cost_share(pcs["objectId"]), "value": canonical_json(pcs)}
        )

    # linkedPlanServices + their children
    for lps in plan.get("linkedPlanServices") or []:
        if _object_id(lps):
            results.append(
                {"key": keys.plan_service(lps["objectId"]), "value": canonical_json(lps)}
            )

        svc = lps.get("linkedService") if isinstance(lps, dict) else None
        if _object_id(svc):
            results.append(
                {"key": keys.service(svc["objectId"]), "value": canonical_json(svc)}
            )

        pscs = lps.get("planserviceCostShares") if isinstance(lps, dict) else None
        if _object_id(pscs):
            results.append(
                {
                    "key": keys.member_cost_share(pscs["objectId"]),
                    "value": canonical_json(pscs),
                }
            )

    return results


# Store all keys for a plan in a single Redis transaction
async def store_plan_graph(plan: Plan, etag: str) -> None:
    kvs = build_redis_writes_from_plan(plan)

    async with redis.pipeline(transaction=True) as pipeline:
        # write all objects
        for kv in kvs:
            pipeline.set(kv["key"], kv["value"])

        # write ETag for the plan
        pipeline.set(keys.plan_etag(plan["objectId"]), etag)

        await pipeline.execute()


async def delete_plan_graph(plan_id: str) -> int:
    plan_key = keys.plan(plan_id)
    canonical = await redis.get(plan_key)
    if not canonical:
        return 0  # nothing to delete

    plan = cast(Plan, json.loads(canonical))

    # dict preserves insertion order, mirroring JS Set iteration order
    keys_to_delete: dict[str, None] = {}

    # whole plan + ETag + per-plan key
    keys_to_delete[keys.plan(plan_id)] = None
    keys_to_delete[keys.plan_etag(plan_id)] = None
    keys_to_delete[keys.plan_object(plan_id)] = None

    # planCostShares
    pcs = plan.get("planCostShares")
    if _object_id(pcs):
        keys_to_delete[keys.plan_cost_share(pcs["objectId"])] = None

    # linkedPlanServices + children
    for lps in plan.get("linkedPlanServices") or []:
        if _object_id(lps):
            keys_to_delete[keys.plan_service(lps["objectId"])] = None
        svc = lps.get("linkedService") if isinstance(lps, dict) else None
        if _object_id(svc):
            keys_to_delete[keys.service(svc["objectId"])] = None
        pscs = lps.get("planserviceCostShares") if isinstance(lps, dict) else None
        if _object_id(pscs):
            keys_to_delete[keys.member_cost_share(pscs["objectId"])] = None

    if len(keys_to_delete) == 0:
        return 0

    async with redis.pipeline(transaction=True) as pipeline:
        for key in keys_to_delete:
            pipeline.delete(key)
        results = await pipeline.execute()

    # sum deleted counts
    deleted = 0
    for count in results or []:
        if isinstance(count, int) and not isinstance(count, bool):
            deleted += count

    return deleted
