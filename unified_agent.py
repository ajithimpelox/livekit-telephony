import asyncio
import json
import traceback
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
    metrics,
)
from livekit import rtc
from livekit.plugins import openai, silero, groq, google, cartesia

from utils.common import (
    logger,
    search_web,
    search_knowledge_base,
    store_long_term_memory_information,
    _RUNTIME,
)
from utils.constants import PROMPTS
from database.db_queries import (
    calculate_credits_used,
    check_customer_credits,
    deduct_customer_credits,
    get_chat_bot_by_id,
    get_agent_custom_prompt,
    get_realtime_information,
    fetch_metadata_by_trunk_phone_number,
    fetch_customer_mcp_server_urls,
)
from tools.rag_tools import get_rag_information_from_vector_store


# -------------------------------
# Unified Agent Implementation
# -------------------------------
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


# -------------------------------
# Entrypoint
# -------------------------------
async def agent_entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Connected to room for agent")

    participant = await ctx.wait_for_participant()
    metadata = json.loads(ctx.job.metadata or "{}")
    logger.info("Participant joined room")

    trunkPhoneNumber = None
    phoneNumber = None
    try:
        if getattr(participant, "kind", None) == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            attrs = getattr(participant, "attributes", {}) or {}
            trunkPhoneNumber = attrs.get("sip.trunkPhoneNumber") or attrs.get("trunkPhoneNumber")
            phoneNumber = attrs.get("sip.phoneNumber") or attrs.get("phoneNumber")
    except Exception:
        pass

    # -------------------------------
    # Inbound vs Outbound Handling
    # -------------------------------
    is_outbound = metadata.get("is_outbound_call")
    if is_outbound:
        logger.info("Outbound call detected, using room metadata.")
    elif trunkPhoneNumber:
        logger.info("Inbound call detected, fetching metadata by trunk phone number.")
        metadata = await fetch_metadata_by_trunk_phone_number(trunkPhoneNumber)

    logger.info(f"Unified metadata: {metadata}")

    customer_id = int(metadata.get("customerId") or 1)
    knowledgebase_id = int(metadata.get("knowledgebaseId") or 1)
    environment = metadata.get("environment")

    # -------------------------------
    # Fetch Chatbot
    # -------------------------------
    existing_chatbot = await get_chat_bot_by_id(knowledgebase_id)
    if not existing_chatbot:
        error_msg = f"Chatbot not found for id: {knowledgebase_id}"
        logger.error(f"Exception {error_msg} {traceback.format_exc()}")
        raise Exception(error_msg)

    # -------------------------------
    # Credit Check
    # -------------------------------
    try:
        credit_check = await check_customer_credits(customer_id, 20)
        if not credit_check.get("has_credits"):
            await asyncio.sleep(2.0)
            if getattr(ctx, "room", None):
                await ctx.room.disconnect()
            return
        logger.info(
            f"Initial credit check passed (credits={credit_check.get('current_credits')}) "
            f"for customer {customer_id}"
        )
    except Exception:
        logger.error("Credit check failed at startup; disconnecting")
        await ctx.room.disconnect()
        return

    # -------------------------------
    # Populate Runtime
    # -------------------------------
    namespace = existing_chatbot.get("namespace")
    index_name = existing_chatbot.get("index_name")

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

    # -------------------------------
    # Knowledge Base & Prompt
    # -------------------------------
    custom_prompt = await get_agent_custom_prompt(knowledgebase_id)
    kb_summary = ""

    try:
        kb_summary_result = await get_rag_information_from_vector_store(
            namespace, index_name, "Summarize the entire document for knowledge base", 1
        )
        if kb_summary_result and kb_summary_result.get("results"):
            kb_summary = "\n".join(
                result[0].page_content
                for result in kb_summary_result["results"]
                if result and len(result) > 0
            )
    except Exception as e:
        logger.warning(f"Failed to get knowledge base summary: {e}")

    agent_mode_instructions = PROMPTS.get("tool_usage_instructions", "")

    final_prompt = (
        PROMPTS.get("realtimePrompt")
        .replace("{AGENT_MODE_INSTRUCTIONS}", agent_mode_instructions)
        .replace("{KBSummary}", kb_summary or "")
        .replace("{customMasterInstructions}", custom_prompt or "")
        .replace("{currentDate}", datetime.now().isoformat())
    )

    print(f"Final prompt: {final_prompt}")

    urls = await fetch_customer_mcp_server_urls(customer_id)
    final_urls = ",".join(urls)
    print(f"MCP server URLs: {final_urls}")

    # -------------------------------
    # Factory Methods
    # -------------------------------
    def create_llm_instance():
        env = (metadata.get("environment") or "groq").lower()
        model_name = metadata.get("llmName")
        try:
            if env == "groq":
                return groq.LLM(
                    model=model_name or "openai/gpt-oss-20b",
                    temperature=0.5,
                    parallel_tool_calls=True,
                    tool_choice="auto",
                )
            elif env == "gemini":
                return google.LLM(model=model_name or "gemini-2.5-flash", tool_choice="auto")
            elif env == "open ai":
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

    def create_tts_instance():
        env = (metadata.get("environment") or "groq").lower()
        voice = metadata.get("voice")
        try:
            if env == "gemini":
                return cartesia.TTS(voice=voice or "f786b574-daa5-4673-aa0c-cbe3e8534c02")
            elif env == "open ai":
                return openai.TTS(voice=voice or "alloy")
            return groq.TTS(
                voice=voice or "Fritz-PlayAI",
                model="playai-tts-arabic"
                if voice in ["Ahmad-PlayAI", "Amira-PlayAI", "Khalid-PlayAI", "Nasser-PlayAI"]
                else "playai-tts",
            )
        except Exception as e:
            logger.error(f"Error creating TTS instance: {e}")
            return openai.TTS(voice="alloy")

    def create_stt_instance():
        try:
            return openai.STT()
        except Exception:
            return openai.STT()

    # -------------------------------
    # Agent Session
    # -------------------------------
    agent = UnifiedAgent(final_prompt)

    try:
        from livekit.agents import mcp as lk_mcp
        mcp_servers = [lk_mcp.MCPServerHTTP(url) for url in final_urls.split(",") if url]
    except Exception:
        mcp_servers = []

    session = AgentSession(
        stt=create_stt_instance(),
        llm=create_llm_instance(),
        tts=create_tts_instance(),
        max_tool_steps=8,
        vad=silero.VAD.load(
            min_speech_duration=0.2,
            min_silence_duration=1.2,
            activation_threshold=0.6,
        ),
        allow_interruptions=False,
        mcp_servers=mcp_servers,
    )

    # -------------------------------
    # Event Handlers
    # -------------------------------
    @session.on("user_input_transcribed")
    def on_user_transcribed(ev: UserInputTranscribedEvent):
        if ev.transcript:
            logger.info(f"USER SAID: {ev.transcript}")

    @session.on("conversation_item_added")
    def on_agent_output(ev: ConversationItemAddedEvent):
        if getattr(ev, "item", None) and getattr(ev.item, "role", None) == "assistant":
            logger.info(f"AGENT SAID: {ev.item.content}")
            ctx.proc.userdata["first_response_sent"] = True   # ✅ mark first reply

    # -------------------------------
    # Background Audio (Thinking only)
    # -------------------------------
    background_audio = BackgroundAudioPlayer(
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=1.2),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    ctx.proc.userdata["background_audio"] = background_audio

    # -------------------------------
    # Start Session
    # -------------------------------
    await session.start(agent=agent, room=ctx.room)
    logger.info("Agent session started")

    # -------------------------------
    # Greeting
    # -------------------------------
    greeting = "Provide a warm, friendly greeting to the user. Keep it brief and welcoming. Make it different each time."
    realtime_information = await get_realtime_information(customer_id)

    if realtime_information:
        greeting_instructions = (
            f"These are the custom relevant information here: {json.dumps(realtime_information)} "
            "Provide a warm greeting to the user. Use the data present in the memory to construct the greeting. "
            "If empty, provide a generic greeting. Reply with audio always. Make it different each time."
        )
        await session.generate_reply(instructions=greeting_instructions)
    else:
        await session.generate_reply(instructions=greeting)

    # -------------------------------
    # Metrics & Credits
    # -------------------------------
    @session.on("metrics_collected")
    def on_metrics_collected(metric: MetricsCollectedEvent):
        if isinstance(metric.metrics, metrics.LLMMetrics):
            total_tokens = metric.metrics.total_tokens
            asyncio.create_task(deduct_credits(customer_id, total_tokens))

    async def deduct_credits(customer_id: int, total_tokens: int):
        total_credits = await calculate_credits_used(total_tokens)
        await deduct_customer_credits(customer_id, total_credits)

    logger.info("Greeting sent for agent")
