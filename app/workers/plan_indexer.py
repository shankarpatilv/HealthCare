import asyncio
import json
import logging
import sys
from typing import Any, cast

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from elasticsearch import ApiError

from app.config import config
from app.services.elasticsearch import es_client, es_index
from app.services.plan_store import Plan
from app.services.queue import PlanEvent

logger = logging.getLogger("indexer")


# Consume messages from RabbitMQ and sync to Elasticsearch
async def main() -> None:
    logger.info("[indexer] starting, connecting to RabbitMQ at %s", config.rabbit_url)

    conn = await aio_pika.connect_robust(config.rabbit_url)
    ch = await conn.channel()

    queue = await ch.declare_queue(config.rabbit_queue, durable=True)
    logger.info("[*] Waiting for messages in queue '%s'", config.rabbit_queue)

    async def on_message(msg: AbstractIncomingMessage) -> None:
        raw = msg.body.decode("utf-8")
        logger.info("[indexer] received message: %s", raw)

        try:
            event = cast(PlanEvent, json.loads(raw))
            logger.info("[indexer] parsed event: %s", event)

            if event["type"] == "delete":
                logger.info("[indexer] handling delete for planId: %s", event["planId"])
                await handle_delete(event["planId"])
            else:
                logger.info(
                    "[indexer] handling upsert for planId: %s type: %s",
                    event["planId"],
                    event["type"],
                )
                await handle_upsert(event["planId"], cast(Plan, event.get("plan")))

            await msg.ack()
            logger.info("[indexer] message ACKed")
        except Exception:
            logger.exception("[indexer] Error handling message:")
            await msg.ack()  # avoid infinite retry for now

    await queue.consume(on_message, no_ack=False)

    # Keep the process alive like the Node event loop
    await asyncio.Future()


# Index / update plan and all children
async def handle_upsert(plan_id: str, plan: Plan) -> None:
    logger.info("[indexer] handleUpsert start for planId: %s", plan_id)
    routing = plan_id
    ops: list[dict[str, Any]] = []

    # 1) Plan (parent)
    ops.append({"index": {"_index": es_index, "_id": plan_id, "routing": routing}})
    ops.append(
        {
            **plan,
            "planId": plan_id,
            "plan_join": {"name": "plan"},  # parent type
        }
    )

    # 2) planCostShares as child of plan
    pcs = plan.get("planCostShares")
    if pcs and pcs.get("objectId"):
        ops.append({"index": {"_index": es_index, "_id": pcs["objectId"], "routing": routing}})
        ops.append(
            {
                **pcs,
                "planId": plan_id,
                "plan_join": {"name": "planCostShares", "parent": plan_id},
            }
        )

    # 3) Each linkedPlanServices and its children
    for lps in plan.get("linkedPlanServices") or []:
        ps_id = lps.get("objectId")
        if not ps_id:
            continue

        # linkedPlanServices as child of plan
        ops.append({"index": {"_index": es_index, "_id": ps_id, "routing": routing}})
        ops.append(
            {
                **lps,
                "planId": plan_id,
                "plan_join": {"name": "linkedPlanServices", "parent": plan_id},
            }
        )

        # linkedService as child of linkedPlanServices
        svc = lps.get("linkedService")
        if svc and svc.get("objectId"):
            ops.append({"index": {"_index": es_index, "_id": svc["objectId"], "routing": routing}})
            ops.append(
                {
                    **svc,
                    "planId": plan_id,
                    "plan_join": {"name": "linkedService", "parent": ps_id},
                }
            )

        # planserviceCostShares as child of linkedPlanServices
        pscs = lps.get("planserviceCostShares")
        if pscs and pscs.get("objectId"):
            ops.append({"index": {"_index": es_index, "_id": pscs["objectId"], "routing": routing}})
            ops.append(
                {
                    **pscs,
                    "planId": plan_id,
                    "plan_join": {"name": "planserviceCostShares", "parent": ps_id},
                }
            )

    logger.info("[indexer] bulk ops count: %s docs", len(ops) // 2)

    if not ops:
        return

    res = await es_client.bulk(refresh=True, operations=ops)
    if res.get("errors"):
        logger.error(
            "[indexer] Elasticsearch bulk upsert errors: %s",
            json.dumps(res.body, indent=2),
        )
    else:
        logger.info("[indexer] bulk upsert OK for planId: %s", plan_id)


# Cascaded delete: parent + all children for this planId
async def handle_delete(plan_id: str) -> None:
    logger.info("[indexer] handleDelete start for planId: %s", plan_id)
    try:
        res = await es_client.delete_by_query(
            index=es_index,
            refresh=True,
            query={"term": {"planId": plan_id}},
        )

        logger.info("[indexer] deleteByQuery result: %s", json.dumps(res.body, indent=2))
    except Exception as err:
        status = err.meta.status if isinstance(err, ApiError) else None
        if status != 404:
            body = err.body if isinstance(err, ApiError) else err
            logger.error("[indexer] Failed cascaded delete in Elasticsearch: %s", body)
        else:
            logger.info("[indexer] deleteByQuery found nothing for planId: %s", plan_id)


async def _run() -> None:
    try:
        await main()
    except Exception:
        logger.exception("[indexer] Plan indexer failed to start:")
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())
