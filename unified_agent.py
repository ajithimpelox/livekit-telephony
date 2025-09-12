import asyncio
import json
import traceback
from typing import Optional, List
from datetime import datetime

from livekit.agents import (
    Agent,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    AutoSubscribe,
    BackgroundAudioPlayer,
    AudioConfig,
    BuiltinAudioClip,
    MetricsCollectedEvent,
    UserInputTranscribedEvent,
    UserStateChangedEvent,
    metrics,
    llm
)
from livekit import rtc
from livekit.plugins import openai, silero, groq, google, cartesia, deepgram

from utils.common import (
    logger,
    search_web,
    search_knowledge_base,
    store_long_term_memory_information,
)
from utils.enums import ChatType
from utils.common import _RUNTIME
from utils.constants import PROMPTS
from database.db_queries import (
    calculate_credits_used,
    check_customer_credits,
    deduct_customer_credits,
    get_chat_bot_by_id,
    get_agent_custom_prompt,
    get_realtime_information,
    fetch_metadata_by_trunk_phone_number,
    fetch_customer_mcp_server_urls
)
from tools.rag_tools import get_rag_information_from_vector_store
from mcp_client.agent_tools import MCPToolsIntegration
from mcp_client.util import MCPUtil
from mcp_client.server import MCPServerHttp
from mcp_client.cache_service import McpServerCacheService


class UnifiedAgent(Agent):
    def __init__(self, prompt: str):
        super().__init__(
            instructions=prompt,
            tools=[
                search_web,
                search_knowledge_base,
                store_long_term_memory_information,
            ],
        )
        self.mode = "voice"
        self._custom_turn_completed_handler = None


async def agent_entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Connected to room for agent")

    participant = await ctx.wait_for_participant()
    metadata = json.loads(ctx.job.metadata or "{}")
    logger.info(f"Participant joined room")
    trunkPhoneNumber = None
    phoneNumber = None
    try:
        if getattr(participant, 'kind', None) == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            attrs = getattr(participant, 'attributes', {}) or {}
            trunkPhoneNumber = attrs.get(
                'sip.trunkPhoneNumber') or attrs.get('trunkPhoneNumber')
            phoneNumber = attrs.get(
                'sip.phoneNumber') or attrs.get('phoneNumber')
    except Exception:
        pass

    is_outbound = metadata.get("isoutBoundCall")
    if is_outbound:
        logger.info("Outbound call detected, using room metadata.")
    elif trunkPhoneNumber:
        logger.info(
            "Inbound call detected, fetching metadata by trunk phone number.")
        metadata = await fetch_metadata_by_trunk_phone_number(trunkPhoneNumber)

    logger.info(f"Unified metadata: {metadata}")
    customer_id = int(metadata.get("customerId") or 1)
    knowledgebase_id = int(metadata.get("knowledgebaseId") or 1)
    environment = metadata.get("environment")

    # existing_chatbot either from metadata.chatbot or fetch
    
    existing_chatbot = await get_chat_bot_by_id(knowledgebase_id)

    if not existing_chatbot:
        error_msg = f"Chatbot not found for id: {knowledgebase_id}"
        logger.error(f"Exception {error_msg} {traceback.format_exc()}")
        raise Exception(error_msg)

    try:
        credit_check = await check_customer_credits(customer_id, 20)
        if not credit_check.get("has_credits"):
            await asyncio.sleep(2.0)
            if getattr(ctx, "room", None):
                await ctx.room.disconnect()
            return
        logger.info(
            f"Initial credit check passed (credits={credit_check.get('current_credits')}) for customer {customer_id}"
        )
    except Exception:
        logger.error("Credit check failed at startup; disconnecting")
        await ctx.room.disconnect()
        return

    # Simplified state (no lead form / presentation)
    is_conversation_active = True

    namespace = existing_chatbot.get("namespace") if existing_chatbot else None
    index_name = existing_chatbot.get(
        "index_name") if existing_chatbot else None

    # Populate shared runtime for tools
    try:
        _RUNTIME.update(
            {
                "room": ctx.room,
                "namespace": namespace,
                "index_name": index_name,
                "customer_id": customer_id,
            }
        )
    except Exception as e:
        logger.warning(f"Failed to populate runtime context: {e}")

    # Get custom prompt and knowledge base summary
    custom_prompt = await get_agent_custom_prompt(knowledgebase_id)
    kb_summary = ""

    # Get knowledge base summary from vector store
    try:
        kb_summary_result = await get_rag_information_from_vector_store(
            namespace, index_name, "Summarize the entire document for knowledge base", 1
        )

        if kb_summary_result and kb_summary_result.get("results"):
            kb_summary = "\n".join(
                [
                    result[0].page_content if result and len(
                        result) > 0 else ""
                    for result in kb_summary_result["results"]
                ]
            )
    except Exception as e:
        logger.warning(f"Failed to get knowledge base summary: {e}")

    agent_mode_instructions = PROMPTS.get("tool_usage_instructions", "")

    # Build final prompt with custom instructions and knowledge base context
    final_prompt = (
        PROMPTS.get("realtimePrompt")
        .replace("{AGENT_MODE_INSTRUCTIONS}", agent_mode_instructions)
        .replace("{KBSummary}", kb_summary or "")
        .replace("{customMasterInstructions}", custom_prompt or "")
        .replace("{currentDate}", datetime.now().isoformat())
    )

    print(f"Final prompt: {final_prompt}")

    urls = await fetch_customer_mcp_server_urls(customer_id)
    print(f"MCP server URLs: {urls}")
    final_urls = ",".join(urls)

    # Select LLM based on metadata environment

    def create_llm_instance():
        environment = metadata.get("environment", "groq").lower()
        model_name = metadata.get("llmName")
        try:
            if environment == "groq":
                return groq.LLM(
                    model=model_name or "openai/gpt-oss-20b",
                    temperature=0.5,
                    parallel_tool_calls=True,
                    tool_choice="auto",
                )
            elif environment == "gemini":
                return google.LLM(
                    model=model_name or "gemini-2.5-flash",
                    tool_choice="auto",
                )
            elif environment == "open ai":
                return openai.LLM(
                    model=model_name or "gpt-5",
                    tool_choice="auto",
                    parallel_tool_calls=True,
                )
        except Exception:   
            return openai.LLM(
            model=model_name or "gpt-4o-mini",
            tool_choice="auto",
            parallel_tool_calls=True,
        )

    # Select TTS based on metadata environment
    def create_tts_instance():
        environment = metadata.get("environment", "groq").lower()
        voice = metadata.get("voice")
        try:
            if environment == "gemini":
                return cartesia.TTS(voice=voice or "f786b574-daa5-4673-aa0c-cbe3e8534c02")
            elif environment == "open ai":
                return openai.TTS(voice=voice or "alloy")
            else:
                return groq.TTS(
                    voice=voice or "Fritz-PlayAI",
                    model="playai-tts-arabic"
                    if voice in [
                        "Ahmad-PlayAI",
                        "Amira-PlayAI",
                        "Khalid-PlayAI",
                        "Nasser-PlayAI",
                    ]
                    else "playai-tts",
                )
        except Exception as e:
            logger.error(f"Error creating TTS instance: {e}")
            return openai.TTS(voice="alloy")

        # Select TTS based on metadata environment

    def create_stt_instance():
        environment = metadata.get("environment", "groq").lower()
        try:
            if environment == "gemini":
                return openai.STT()
            elif environment == "open ai":
                return openai.STT()
            else:
                print("Using deepgram whisper-large")
                return openai.STT()
        except Exception as e:
            return openai.STT()

    agent = UnifiedAgent(final_prompt)

    print(f"Final URLs: {final_urls}")
    # Try optional MCP integration
    try:
        from livekit.agents import mcp as lk_mcp
        mcp_servers = [lk_mcp.MCPServerHTTP(url)
                       for url in final_urls.split(",") if url]
    except Exception:
        mcp_servers = []


    session = AgentSession(
        preemptive_generation=True,
        llm=create_llm_instance(),
        tts=create_tts_instance(),
        stt=create_stt_instance(),
        max_tool_steps=8,
        vad=silero.VAD.load(
        min_speech_duration=0.2,      # must speak at least 200ms
        min_silence_duration=1.2,     # needs 1.2s of silence before ending speech
        activation_threshold=0.6      # slightly stricter speech detection
        ),
        allow_interruptions=True,
        mcp_servers=mcp_servers,
    )

    # def save_transcription_to_db(text: str, speaker_type: str):
    #     if not text:
    #         return
        
    #     call_log_id = conversation_id
    #     if not call_log_id:
    #         logger.warning("Could not save transcription to DB, no conversation_id")
    #         return

    #     payload = {
    #         "call_log_id": call_log_id,
    #         "text": text,
    #         "type": speaker_type,
    #         "character_count": len(text),
    #         "status": 1,
    #         "created_datetime": datetime.utcnow().isoformat()
    #     }
        
    #     try:
    #         # Not using async requests here to avoid adding a new dependency (httpx)
    #         # This is a quick operation, so it should be fine.
    #         requests.post("http://localhost:3000/api/call-transcriptions", json=payload, timeout=2)
    #     except Exception as e:
    #         logger.error(f"Failed to save transcription to DB: {e}")


    @session.on("user_input_transcribed")
    def on_user_transcribed(ev: UserInputTranscribedEvent):
        if ev.transcript:
            logger.info(f"USER SAID: {ev.transcript}")
            # save_transcription_to_db(ev.text, "user")


    @session.on("conversation_item_added")
    def on_agent_output(ev: ConversationItemAddedEvent):
        if getattr(ev, "item", None) and getattr(ev.item, "role", None) == "assistant":
            logger.info(f"AGENT SAID: {ev.item.content}")
            # save_transcription_to_db(ev.response.text, "ai")
    
    # Create background audio player for thinking sounds only (no continuous ambient sound)
    # This will only play during response generation, not continuously
    background_audio = BackgroundAudioPlayer(
        # Remove ambient_sound to stop continuous background audio
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=1.2),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    # Save for later use inside message processing
    ctx.proc.userdata["background_audio"] = background_audio

    await session.start(agent=agent, room=ctx.room)
    logger.info("Agent session started")

    greeting = (
        f"Provide a warm, friendly greeting to the user. Keep it brief and welcoming. Make it different each time."
    )

    # Removed initialize_presentation

    # Always send greeting (simplified flow)
    realtime_information = await get_realtime_information(customer_id)
    if len(realtime_information) > 0:
        greeting_instructions = (
            f"These are the custom relevant information here: {json.dumps(realtime_information)}"
            + "Provide a warm greeting to the user. Use the data present in the memory to construct the greeting. Add some flavor text using the information provided. If it is empty provide a generic greeting. Reply with audio always. Make it different each time"
        )
        await session.generate_reply(instructions=greeting_instructions)
    else:
        await session.generate_reply(instructions=greeting)

    @session.on("metrics_collected")
    def on_metrics_collected(metric: MetricsCollectedEvent):
        if isinstance(metric.metrics, metrics.LLMMetrics):
            print(f"Metrics collected: {metrics}")
            total_tokens = metric.metrics.total_tokens
            asyncio.create_task(deduct_credits(customer_id, total_tokens))

    async def deduct_credits(customer_id: int, total_tokens: int):
        totalCredits = await calculate_credits_used(total_tokens)
        await deduct_customer_credits(customer_id, totalCredits)

    logger.info(f"Greeting sent for agent")

    # # # Cleanup function for MCP servers and cache
    # # async def _cleanup():
    # #     try:
    # #         # Clear cache entries related to this context
    # #         try:
    # #             cache_service.clear_customer_cache(customer_id)
    # #             cache_service.clear_all()
    # #         except Exception:
    # #             pass
    # #     except Exception:
    # #         pass

    # # Bind cleanup on disconnect (best-effort across SDK versions)
    # try:
    #     if hasattr(ctx.room, "on"):
    #         ctx.room.on("disconnected",
    #                     lambda: asyncio.create_task(_cleanup()))
    #         ctx.room.on(
    #             "participant_disconnected",
    #             lambda *args, **kwargs: asyncio.create_task(_cleanup()),
    #         )
    #     elif hasattr(ctx.room, "on_disconnected"):
    #         ctx.room.on_disconnected(lambda: asyncio.create_task(_cleanup()))
    # except Exception:
    #     pass
