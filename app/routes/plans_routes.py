import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from app.middleware.auth import validate_bearer_token
from app.middleware.validation import validate_plan, validate_plan_body
from app.services.etag import compute_etag_from_json
from app.services.plan_store import Plan, delete_plan_graph, store_plan_graph
from app.services.queue import publish_plan_event
from app.services.redis import keys, redis
from app.utils.merge import smart_merge

router = APIRouter(dependencies=[Depends(validate_bearer_token)])


# POST /api/v1/plans – Create if not exists
@router.post("")
async def create_plan(body: dict = Depends(validate_plan_body)):
    plan = body
    id = plan.get("objectId")
    if not id:
        raise HTTPException(400, "objectId is required")

    key = keys.plan(id)
    exists = await redis.exists(key)
    if exists:
        raise HTTPException(409, f"Plan with id {id} already exists")

    etag = compute_etag_from_json(plan)

    # writes whole plan, per-object keys, and ETag
    await store_plan_graph(plan, etag)

    await publish_plan_event({
        "type": "create",
        "planId": id,
        "plan": plan,
    })

    return JSONResponse(status_code=201, content=plan, headers={"ETag": etag})


# GET /api/v1/plans – Return all plans
@router.get("")
async def get_all_plans():
    plan_keys: list[str] = []
    cursor = 0

    while True:
        cursor, keys_batch = await redis.scan(cursor, match="plans:*", count=100)
        for key in keys_batch:
            if not key.endswith(":etag"):
                plan_keys.append(key)
        if cursor == 0:
            break

    if len(plan_keys) == 0:
        return JSONResponse(status_code=200, content=[])

    canonical_plans = await redis.mget(plan_keys)
    plans = [json.loads(canonical) for canonical in canonical_plans if canonical]

    return JSONResponse(status_code=200, content=plans)


# GET /api/v1/plans/:id – Conditional read with If-None-Match
@router.get("/{id}")
async def get_plan(id: str, request: Request):
    key = keys.plan(id)

    canonical, etag = await redis.mget(key, keys.plan_etag(id))
    if not canonical:
        raise HTTPException(404, "Plan not found")

    current_etag: str = etag if etag is not None else compute_etag_from_json(json.loads(canonical))
    if_none_match = request.headers.get("If-None-Match")

    if if_none_match and if_none_match == current_etag:
        return Response(status_code=304)

    return Response(
        content=canonical,
        status_code=200,
        media_type="application/json",
        headers={"ETag": current_etag},
    )


@router.delete("/{id}")
async def delete_plan(id: str):
    deleted = await delete_plan_graph(id)

    if deleted == 0:
        raise HTTPException(404, "Plan not found")

    await publish_plan_event({
        "type": "delete",
        "planId": id,
    })

    return Response(status_code=204)


# PUT /api/v1/plans/:id — Full update with If-Match
@router.put("/{id}")
async def update_plan(id: str, request: Request, body: dict = Depends(validate_plan_body)):
    plan: Plan = body

    if plan.get("objectId") != id:
        raise HTTPException(400, "objectId in body must match URL parameter")

    key = keys.plan(id)
    canonical, current_etag = await redis.mget(key, keys.plan_etag(id))

    if not canonical:
        raise HTTPException(404, "Plan not found")

    # Conditional write: check If-Match
    if_match = request.headers.get("If-Match")
    if if_match and if_match != current_etag:
        raise HTTPException(412, "Precondition Failed: ETag mismatch")

    # Plan is already validated by validate_plan_body
    new_etag = compute_etag_from_json(plan)

    # Write whole plan + all per-object keys + ETag
    await store_plan_graph(plan, new_etag)
    await publish_plan_event({
        "type": "update",
        "planId": id,
        "plan": plan,
    })

    return JSONResponse(status_code=200, content=plan, headers={"ETag": new_etag})


# PATCH /api/v1/plans/:id — Partial update with merge and If-Match
@router.patch("/{id}")
async def patch_plan(id: str, request: Request):
    try:
        updates = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON body")

    key = keys.plan(id)
    canonical, current_etag = await redis.mget(key, keys.plan_etag(id))

    if not canonical:
        raise HTTPException(404, "Plan not found")

    # Conditional write: check If-Match
    if_match = request.headers.get("If-Match")
    if if_match and if_match != current_etag:
        raise HTTPException(412, "Precondition Failed: ETag mismatch")

    existing_plan: Plan = json.loads(canonical)
    merged_plan: Plan = smart_merge(existing_plan, updates)

    # Validate merged result against schema
    errors = validate_plan(merged_plan)
    if errors:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Merged plan fails validation",
                "details": errors,
            },
        )

    new_etag = compute_etag_from_json(merged_plan)

    # Write whole merged plan + all per-object keys + ETag
    await store_plan_graph(merged_plan, new_etag)
    await publish_plan_event({
        "type": "update",
        "planId": id,
        "plan": merged_plan,
    })

    return JSONResponse(status_code=200, content=merged_plan, headers={"ETag": new_etag})


# Helper function for deep merge
def _deep_merge(target: Any, source: Any) -> Any:
    output = {**target}

    for key in source:
        if source[key] and isinstance(source[key], dict):
            output[key] = _deep_merge(target.get(key) or {}, source[key])
        else:
            output[key] = source[key]

    return output
