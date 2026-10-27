"""Port of tests/plans.test.ts ("Plan API").

Tests run in file order and share state (one module-scoped client / redis),
exactly like the sequential jest suite.
"""

import copy

SAMPLE_PLAN = {
    "planCostShares": {
        "deductible": 2000,
        "_org": "example.com",
        "copay": 23,
        "objectId": "1234vxc2324sdf-501",
        "objectType": "membercostshare",
    },
    "linkedPlanServices": [
        {
            "linkedService": {
                "_org": "example.com",
                "objectId": "1234520xvc30asdf-502",
                "objectType": "service",
                "name": "Yearly physical",
            },
            "planserviceCostShares": {
                "deductible": 10,
                "_org": "example.com",
                "copay": 0,
                "objectId": "1234512xvc1314asdfs-503",
                "objectType": "membercostshare",
            },
            "_org": "example.com",
            "objectId": "27283xvx9asdff-504",
            "objectType": "planservice",
        },
    ],
    "_org": "example.com",
    "objectId": "12xvxc345ssdsds-508",
    "objectType": "plan",
    "planType": "inNetwork",
    "creationDate": "12-12-2017",
}

PLAN_ID = SAMPLE_PLAN["objectId"]


def sample_plan():
    return copy.deepcopy(SAMPLE_PLAN)


def test_post_plans_creates_plan_returns_201_with_etag(client):
    res = client.post("/api/v1/plans", json=sample_plan())

    assert res.status_code == 201
    assert res.headers.get("etag") is not None
    assert res.json()["objectId"] == PLAN_ID


def test_get_plans_returns_all_plans(client):
    res = client.get("/api/v1/plans")

    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    ids = [plan["objectId"] for plan in body]
    assert PLAN_ID in ids


def test_get_plan_by_id_returns_etag_and_supports_304(client):
    first = client.get(f"/api/v1/plans/{PLAN_ID}")
    assert first.status_code == 200
    assert first.headers.get("etag") is not None

    etag = first.headers["etag"]
    not_modified = client.get(
        f"/api/v1/plans/{PLAN_ID}", headers={"If-None-Match": etag}
    )

    assert not_modified.status_code == 304


def test_post_plans_duplicate_object_id_returns_409(client):
    res = client.post("/api/v1/plans", json=sample_plan())

    assert res.status_code == 409


def test_delete_plan_then_get_returns_404(client):
    deleted = client.delete(f"/api/v1/plans/{PLAN_ID}")
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/plans/{PLAN_ID}")
    assert missing.status_code == 404

    listing = client.get("/api/v1/plans")
    assert listing.status_code == 200
    body = listing.json()
    assert isinstance(body, list)
    ids = [plan["objectId"] for plan in body]
    assert PLAN_ID not in ids
