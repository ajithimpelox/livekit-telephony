PROMPTS = {
    "realtimePrompt": (
        "{AGENT_MODE_INSTRUCTIONS}\n\n"
        "Today is {currentDate}.\n\n"
        "Knowledge Base Summary:\n{KBSummary}\n\n"
        "Custom Instructions:\n{customMasterInstructions}"
    ),
    "presentation_instructions": "You are a presentation agent. Narrate slides concisely and clearly.",
    "tool_usage_instructions": "You are a helpful voice assistant. Use tools when helpful.",
}
