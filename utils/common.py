import json
import logging
import asyncio
from typing import Optional
from datetime import datetime
import os
from tavily import TavilyClient
from livekit.agents import (
    JobProcess,
    function_tool,
    RunContext,
    ChatMessage,
)
from livekit.plugins import silero
from livekit import rtc
from dotenv import load_dotenv
from tools.rag_tools import get_rag_information_from_vector_store
from livekit import api


load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def prewarm(proc: JobProcess):
    logger.info("=== PREWARM FUNCTION CALLED ===")
    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("VAD loaded successfully in prewarm")
    except Exception as e:
        logger.error(f"Error in prewarm: {e}")
        raise

# Minimal runtime container used by tools.
_RUNTIME: dict = {
    "room": None,
    "namespace": None,
    "index_name": None,
    "customer_id": None,
}

# --------------------------
# Generic send helper
# --------------------------
async def send_text_message(room: rtc.Room, topic: str, message: str, additional_data: dict = None):
    """Send structured text message back to frontend"""
    try:
        data = {
            "topic": topic,
            "message": message,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        if additional_data:
            data.update(additional_data)
        data_bytes = json.dumps(data).encode("utf-8")

        if getattr(room, "local_participant", None):
            await room.local_participant.publish_data(
                payload=data_bytes,
                reliable=True,
                topic=topic
            )
            logger.info(f"📡 Sent event topic={topic}, message={message[:50]}..., additional_data={additional_data}")
    except Exception as e:
        logger.error(f"Failed to send text message: {e}")


# --------------------------
# Tools
# --------------------------
@function_tool()
async def search_web(context: RunContext, query: Optional[str] = None) -> str:
    """Search the web for real-time information."""
    # Derive query if missing
    effective_query = (query or "").strip()
    if not effective_query:
        try:
            for item in reversed(context.speech_handle.chat_items):
                if isinstance(item, ChatMessage) and item.role == "user":
                    if item.text_content:
                        effective_query = item.text_content
                        break
        except Exception:
            pass
    if not effective_query:
        return "Please specify what to search for."

    try:
        if _RUNTIME.get("room"):
            await send_text_message(_RUNTIME["room"], "message", "Searching the web...")
    except Exception as e:
        logger.warning(f"Notify frontend failed: {e}")

    logger.info(f":mag: Searching the web for: {effective_query}")
    try:
        tavily_client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        response = tavily_client.search(
            query=effective_query,
            search_depth="advanced",
            include_answer=True,
            max_results=5,
        )
        answer = response.get("answer")
        results = response.get("results", [])

        unique_sources = {r["url"]: r for r in results if r.get("url")}
        source_urls = list(unique_sources.keys())[:5]

        if _RUNTIME.get("room") and source_urls:
            await send_text_message(
                _RUNTIME["room"], "web-search-sources", "", {"sources": source_urls}
            )

        final_answer = answer or "I couldn't find specific information about that."
        return f"Here's what I found:\n\n{final_answer}"
    except Exception as e:
        logger.error(f"Web search failed: {e}")
        return f"I encountered an error while searching: {str(e)}"


@function_tool()
async def search_knowledge_base(context: RunContext, query: Optional[str] = None) -> str:
    """Search the internal knowledge base."""
    effective_query = (query or "").strip()
    if not effective_query:
        try:
            for item in reversed(context.speech_handle.chat_items):
                if isinstance(item, ChatMessage) and item.role == "user":
                    if item.text_content:
                        effective_query = item.text_content
                        break
        except Exception:
            pass
    if not effective_query:
        return "Please specify what to search for in the knowledge base."

    try:
        if _RUNTIME.get("room"):
            await send_text_message(_RUNTIME["room"], "message", "Searching knowledge base...")
    except Exception as e:
        logger.warning(f"Notify frontend failed: {e}")

    namespace, index_name = _RUNTIME.get("namespace"), _RUNTIME.get("index_name")
    if not namespace or not index_name:
        return "Knowledge base is not configured yet. I'll answer with general knowledge instead."

    try:
        kb = await get_rag_information_from_vector_store(
            namespace=namespace, index_name=index_name, message=effective_query, top_k=1
        )
        results = (kb or {}).get("results") or []
        if results:
            doc = results[0][0]
            page_content = getattr(doc, "page_content", "") or getattr(doc, "pageContent", "")
            page_number = None
            try:
                page_number = getattr(doc, "metadata", {}).get("page")
            except Exception:
                if hasattr(doc, "metadata"):
                    page_number = doc.metadata.get("page")

            if _RUNTIME.get("room") and page_number:
                await send_text_message(
                    _RUNTIME["room"], "presentation-page-number", "", {"pageNumber": page_number}
                )
            if page_content:
                return f"Based on your query:\n\n{page_content}"

        return f"No specific info about '{effective_query}' in KB. Falling back to general knowledge."
    except Exception as e:
        logger.error(f"KB search failed: {e}")
        return f"Error accessing KB. Falling back to general knowledge on '{effective_query}'."


@function_tool()
async def store_long_term_memory_information(context: RunContext, key: str, value: str) -> str:
    """Store important info in DB."""
    customer_id = _RUNTIME.get("customer_id")
    try:
        if _RUNTIME.get("room"):
            await send_text_message(_RUNTIME["room"], "message", "Storing info in memory...")
        from database.db_queries import upsert_customer_realtime_information
        await upsert_customer_realtime_information(customer_id=customer_id, key=key, value=value)
        return "Stored successfully in memory"
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        return f"Failed to store info: {str(e)}"

