from elasticsearch import AsyncElasticsearch

from app.config import config

es_client = AsyncElasticsearch(config.elastic_url)

es_index = config.elastic_index
