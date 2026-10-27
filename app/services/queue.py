import json
import logging
from typing import Literal, TypedDict, Union

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from app.config import config
from app.services.plan_store import Plan

logger = logging.getLogger(__name__)


class DeletePlanEvent(TypedDict):
    type: Literal["delete"]
    planId: str


class UpsertPlanEvent(TypedDict):
    type: Literal["create", "update"]
    planId: str
    plan: Plan


PlanEvent = Union[DeletePlanEvent, UpsertPlanEvent]

_connection: AbstractRobustConnection | None = None
_channel: AbstractChannel | None = None


async def get_channel() -> AbstractChannel:
    global _connection, _channel
    if _channel and not _channel.is_closed:
        return _channel

    _connection = await aio_pika.connect_robust(config.rabbit_url)
    ch = await _connection.channel()
    await ch.declare_queue(config.rabbit_queue, durable=True)

    _channel = ch
    return ch


async def publish_plan_event(event: PlanEvent) -> None:
    ch = await get_channel()
    message = aio_pika.Message(
        body=json.dumps(event).encode("utf-8"),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    await ch.default_exchange.publish(message, routing_key=config.rabbit_queue)
