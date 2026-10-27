from redis.asyncio import Redis

from app.config import config

redis = Redis.from_url(config.redis_url, decode_responses=True)


class keys:
    # existing
    @staticmethod
    def plan(id: str) -> str:
        return f"plans:{id}"

    @staticmethod
    def plan_etag(id: str) -> str:
        return f"plans:{id}:etag"

    # new per-object keys, aligned with objectType
    @staticmethod
    def plan_object(id: str) -> str:
        return f"plan:{id}"

    @staticmethod
    def plan_cost_share(id: str) -> str:
        return f"planCostShare:{id}"

    @staticmethod
    def plan_service(id: str) -> str:
        return f"planService:{id}"

    @staticmethod
    def service(id: str) -> str:
        return f"service:{id}"

    @staticmethod
    def member_cost_share(id: str) -> str:
        return f"memberCostShare:{id}"
