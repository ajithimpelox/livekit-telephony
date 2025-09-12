#!/usr/bin/env python3
"""
Trigger Outgoing Call Script

This script allows you to initiate outgoing calls for testing purposes.
It creates an agent dispatch and makes a SIP call to the specified phone number.

Usage:
    python trigger_outgoing_call.py
    
Or modify the phone_number variable below and run the script.
"""

import asyncio
import json
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from livekit import api

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("trigger-outgoing-call")

# Configuration
# This should match the agent name in main.py
AGENT_NAME = "telephone-enhanced-agent"
OUTBOUND_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID")


async def make_outgoing_call(phone_number: str, room_name: str = None):
    """
    Create a dispatch and add a SIP participant to call the phone number

    Args:
        phone_number: The phone number to call (e.g., "+1234567890")
        room_name: Optional room name, defaults to ROOM_NAME
    """
    if room_name is None:
        room_name = 'telephone-enhanced-room'

    logger.info(f"Initiating outgoing call to {phone_number}")

    # Validate environment variables
    if not OUTBOUND_TRUNK_ID or not OUTBOUND_TRUNK_ID.startswith("ST_"):
        logger.error("SIP_OUTBOUND_TRUNK_ID is not set or invalid")
        logger.error(
            "Please check your .env file and ensure SIP_OUTBOUND_TRUNK_ID is properly configured")
        return False

    lkapi = api.LiveKitAPI()

    try:
        # Create agent dispatch
        logger.info(
            f"Creating dispatch for agent {AGENT_NAME} in room {room_name}")
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=json.dumps({
                  'userSessionId': '7cd34768-8183-4da3-8ab4-6a2277c7e248',
 'conversationId': '56045-1757538652039', 
'knowledgebaseId': 4207,
 'customerId': 1492,
 'voice': 'f786b574-daa5-4673-aa0c-cbe3e8534c02',
 'enableStream': 'true', 
'llmName': 'gemini-2.5-pro',
 'namespace': 'chatbot-1492-ak-normal-1756890436786', 
'indexName': 'chatbot-01', 
'customPrompt': 'Use the following pieces of context to answer the question at the end.',
 'workflowDetails': None, 
'integrationsEnabled': ['twilio'], 
'timestamp': 1757538653499,
 'isEmbedSharedChatbot': False,
 'environment': 'gemini',
 'isoutBoundCall': True,
                })
            )
        )
        logger.info(f"Created dispatch: {dispatch}")

        # Create SIP participant to make the call
        logger.info(f"Dialing {phone_number} to room {room_name}")

        sip_participant = await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room_name,
                krisp_enabled=False,
                sip_trunk_id=OUTBOUND_TRUNK_ID,
                sip_call_to=phone_number,
                participant_identity="phone_user",
                participant_name=f"Caller to {phone_number}",
            )
        )
        logger.info(f"Created SIP participant: {sip_participant}")
        logger.info(f"Call initiated successfully to {phone_number}")

        return True

    except Exception as e:
        logger.error(f"Error creating outgoing call: {e}")
        return False

    finally:
        # Close API connection
        await lkapi.aclose()


async def test_outgoing_call():
    """
    Test function to make an outgoing call
    Modify the phone_number below to test with your desired number
    """
    # MODIFY THIS PHONE NUMBER FOR TESTING
    phone_number = "+917845512947"  # Replace with your test phone number

    logger.info("=== Outgoing Call Test ===")
    logger.info(f"Target phone number: {phone_number}")
    logger.info(f"Agent name: {AGENT_NAME}")
    logger.info(f"Outbound trunk ID: {OUTBOUND_TRUNK_ID}")

    success = await make_outgoing_call(phone_number, 'telephone_enhanced_agent')

    if success:
        logger.info("\n=== Call Status ===")
        logger.info("✅ Outgoing call initiated successfully!")
        logger.info("\n=== Next Steps ===")
        logger.info(
            "1. The call should be connecting to the specified phone number")
        logger.info(
            "2. Make sure your main.py IVR agent is running to handle the call")
        logger.info("3. Answer the phone to interact with the IVR agent")
        logger.info("4. Check the agent logs for call processing details")
    else:
        logger.error("\n=== Call Failed ===")
        logger.error("❌ Failed to initiate outgoing call")
        logger.error("Please check your configuration and try again")


def main():
    """
    Main function to trigger outgoing call
    """
    logger.info("Starting Outgoing Call Trigger...")

    # Verify required environment variables
    required_vars = [
        'LIVEKIT_URL',
        'LIVEKIT_API_KEY',
        'LIVEKIT_API_SECRET',
        'SIP_OUTBOUND_TRUNK_ID'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please check your .env file")
        return

    # Run the test
    asyncio.run(test_outgoing_call())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Outgoing call trigger stopped by user")
    except Exception as e:
        logger.error(f"Error in outgoing call trigger: {e}")
        raise
