from typing import List


class McpServerCacheService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = McpServerCacheService()
        return cls._instance

    async def get_mcp_server_urls(self, customer_id: int, is_embed_shared_chatbot: bool, knowledgebase_id: int, uuid: str = None) -> List[str]:
        # Return empty list by default; can be populated from config in real impl
        return []

    def clear_shared_chatbot_cache(self, customer_id: int, knowledgebase_id: int, uuid: str):
        return None

    def clear_customer_cache(self, customer_id: int):
        return None

    def clear_all(self):
        return None
