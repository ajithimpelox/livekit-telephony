# LiveKit Telephony IVR System

A consolidated LiveKit telephony project for handling both incoming and outgoing calls with an IVR agent.

## Project Structure

```
livekit-telephony/
├── .env                    # Environment configuration
├── main.py                 # Main IVR agent for incoming calls
├── trigger_outgoing_call.py # Script to trigger outgoing calls
├── telephony/              # Supporting telephony modules
│   ├── answer_call.py      # Call answering utilities
│   ├── sip_lifecycle.py    # SIP lifecycle management
│   └── warm_handoff.py     # Call transfer functionality
└── venv-3.12/              # Python virtual environment
```

## Setup

1. **Environment Configuration**
   - Ensure your `.env` file contains all required variables:
     ```
     LIVEKIT_URL=wss://your-livekit-url
     LIVEKIT_API_KEY=your-api-key
     LIVEKIT_API_SECRET=your-api-secret
     SIP_OUTBOUND_TRUNK_ID=ST_your-outbound-trunk-id
     SIP_INBOUND_TRUNK_ID=ST_your-inbound-trunk-id
     OPENAI_API_KEY=your-openai-api-key
     DEEPGRAM_API_KEY=your-deepgram-api-key
     ```

2. **Virtual Environment**
   ```bash
   # Activate the virtual environment
   venv-3.12\Scripts\activate  # Windows
   # or
   source venv-3.12/bin/activate  # Linux/Mac
   ```

## Usage

### Starting the IVR Agent (Incoming Calls)

To start receiving incoming calls:

```bash
python main.py
```

This will:
- Start the IVR agent
- Listen for incoming calls on your configured SIP trunk
- Automatically handle and route incoming calls
- Provide interactive voice responses

### Triggering Outgoing Calls

To make an outgoing call for testing:

```bash
python trigger_outgoing_call.py
```

This will:
- Create an agent dispatch
- Initiate a SIP call to the configured phone number
- Connect the call to the IVR agent

**To customize the target phone number:**
1. Edit `trigger_outgoing_call.py`
2. Modify the `phone_number` variable in the `test_outgoing_call()` function
3. Run the script

## Features

- **Incoming Call Handling**: Automatic reception and processing of incoming calls
- **Outgoing Call Initiation**: Programmatic outgoing call triggering
- **IVR Functionality**: Interactive voice response with AI-powered conversations
- **Call Transfer**: Warm handoff capabilities to human agents
- **SIP Integration**: Full SIP trunk support for telephony operations

## Logs and Monitoring

- Both scripts provide detailed logging for call status and processing
- Monitor the console output for real-time call information
- Check for any configuration errors in the logs

## Troubleshooting

1. **Environment Variables**: Ensure all required variables are set in `.env`
2. **SIP Trunk Configuration**: Verify your SIP trunk IDs are correct
3. **Network Connectivity**: Check your LiveKit server connectivity
4. **API Keys**: Validate your OpenAI and Deepgram API keys

## Support Files

The `telephony/` directory contains supporting modules:
- `answer_call.py`: Utilities for call answering
- `sip_lifecycle.py`: SIP call lifecycle management
- `warm_handoff.py`: Call transfer functionality

These are automatically used by the main scripts and don't need to be run directly.