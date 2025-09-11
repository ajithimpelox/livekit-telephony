# LiveKit Telephony Agent

A consolidated LiveKit telephony project for handling both incoming and outgoing calls with a powerful, AI-driven agent.

## Project Structure

```
livekit-telephony/
├── .env                    # Environment configuration
├── main.py                 # Main entrypoint for the LiveKit agent
├── unified_agent.py        # Core agent logic
├── trigger_outgoing_call.py # Script to initiate outgoing calls for testing
├── agent.py                # Agent entrypoint resolver
├── database/               # Database interaction logic
│   ├── db_queries.py       # Functions for querying the database
│   └── mysql/
│       └── db_manager.py   # MySQL database manager
├── mcp_client/             # MCP (Multi-platform Communication Protocol) client
│   ├── agent_tools.py      # Tools for agent interaction with MCP
│   ├── cache_service.py    # Caching for MCP
│   ├── server.py           # MCP server interaction
│   └── util.py             # MCP utilities
├── tools/                  # Agent tools
│   └── rag_tools.py        # RAG (Retrieval-Augmented Generation) tools
├── utils/                  # Utility functions and constants
│   ├── common.py           # Common utility functions
│   ├── constants.py        # Project constants
│   └── enums.py            # Enumerations
└── venv-3.12/              # Python virtual environment
```

## Setup

1.  **Environment Configuration**
    -   Ensure your `.env` file contains all required variables:
        ```
        LIVEKIT_URL=wss://your-livekit-url
        LIVEKIT_API_KEY=your-api-key
        LIVEKIT_API_SECRET=your-api-secret
        SIP_OUTBOUND_TRUNK_ID=ST_your-outbound-trunk-id
        # Add other necessary environment variables for database, LLMs, etc.
        # e.g. DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
        # e.g. OPENAI_API_KEY, GROQ_API_KEY, GOOGLE_API_KEY
        ```

2.  **Virtual Environment**
    ```bash
    # Activate the virtual environment
    venv-3.12\Scripts\activate  # Windows
    # or
    source venv-3.12/bin/activate  # Linux/Mac
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Starting the Agent (for incoming calls)

To start the agent and listen for incoming calls:

```bash
python main.py
```

This will:
- Start the LiveKit agent.
- Listen for incoming SIP calls on your configured trunk.
- Route incoming calls to the `UnifiedAgent`.

### Triggering Outgoing Calls

To make an outgoing call for testing purposes:

```bash
python trigger_outgoing_call.py
```

This will:
- Create an agent dispatch job.
- Initiate a SIP call to the phone number configured in the script.
- Connect the call to the `UnifiedAgent`.

**To customize the target phone number:**
1.  Edit `trigger_outgoing_call.py`
2.  Modify the `phone_number` variable in the `test_outgoing_call()` function.
3.  Run the script.

## Call Flow

### Inbound Call
1.  A SIP call is received by the LiveKit server.
2.  LiveKit creates a room and a job for the `telephone-enhanced-agent`.
3.  `main.py` starts the agent.
4.  `unified_agent.py`'s `agent_entrypoint` is invoked.
5.  The agent fetches metadata (e.g., chatbot ID, customer ID) from the database using the SIP trunk phone number.
6.  The agent checks for customer credits.
7.  A prompt is constructed using a base prompt, custom instructions, and a knowledge base summary.
8.  The agent session starts, and a greeting is sent to the caller.
9.  The agent interacts with the caller using LLM, TTS, and STT.

### Outbound Call
1.  The `trigger_outgoing_call.py` script is executed.
2.  The script creates an agent dispatch job with specified metadata (e.g., chatbot ID, customer ID, phone number).
3.  LiveKit initiates a SIP call to the specified phone number.
4.  When the call is answered, the participant is connected to the room with the agent.
5.  The agent flow is similar to the inbound call, but it uses the metadata provided in the dispatch request.

## Features

-   **Inbound and Outbound Calls**: Handles both incoming and outgoing PSTN calls via SIP.
-   **AI-Powered Agent**: Utilizes Large Language Models (LLMs) for natural conversations.
-   **Dynamic Provider Selection**: Dynamically selects LLM, Text-to-Speech (TTS), and Speech-to-Text (STT) providers (e.g., Groq, OpenAI, Google) based on call metadata.
-   **Knowledge Base Integration**: Uses Retrieval-Augmented Generation (RAG) to provide answers from a knowledge base.
-   **Credit Management**: Checks and deducts customer credits for using the service.
-   **Database Integration**: Fetches agent configuration and logs chat transactions to a database.
-   **MCP Integration**: Supports Multi-platform Communication Protocol for advanced communication scenarios.

## Logs and Monitoring

-   The agent provides detailed logging for the entire call lifecycle.
-   Monitor the console output for real-time information and potential errors.

## Troubleshooting

1.  **Environment Variables**: Ensure all required variables are correctly set in the `.env` file.
2.  **SIP Trunk Configuration**: Verify that your SIP trunk IDs are correct in the LiveKit project settings and your `.env` file.
3.  **Database Connection**: Check if the database credentials in your `.env` file are correct and the database is accessible.
4.  **API Keys**: Make sure the API keys for your selected LLM, TTS, and STT providers are valid.