import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    port: int = int(os.getenv("PORT", "8080"))
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
    env: str = os.getenv("NODE_ENV", "development")
    rabbit_url: str = os.getenv("RABBITMQ_URL", "amqp://localhost")
    rabbit_queue: str = os.getenv("RABBITMQ_QUEUE", "plan-events")

    elastic_url: str = os.getenv("ELASTIC_URL", "http://localhost:9200")
    elastic_index: str = os.getenv("ELASTIC_INDEX", "demo")


config = Config()
