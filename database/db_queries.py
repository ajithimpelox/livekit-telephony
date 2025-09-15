from utils.common import logger
from utils.enums import ChatType
from database.mysql.db_manager import connection_pool # type: ignore

async def get_chat_bot_by_id(chat_bot_id: int):
    try:
        print(f"Getting chat bot by id: {chat_bot_id}")
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)
        chat_bot_query = f"""SELECT * FROM chat_bot WHERE chat_bot_id='{chat_bot_id}'"""
        cursor.execute(chat_bot_query)
        result = cursor.fetchone()
        cursor.close()
        connection_object.close()
        return result
    except Exception as e:
        logger.error(f"Error getting chat bot by id: {e}")
        return None


async def get_chat_bot_by_trunk_phone_number(trunk_phone_number: str):
    """Fetch a chat bot record by associated trunk phone number.

    Assumptions (adjust to match your schema):
      - Mapping table: chat_bot_phone_number (chat_bot_phone_number_id, chat_bot_id, trunk_phone_number, status)
      - chat_bot table primary key: chat_bot_id
      - Active rows have status = 1

    Returns the chatbot row (dict) or None. Adds safe default keys similar to get_chat_bot_by_id.
    """
    if not trunk_phone_number:
        return None
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)
        query = (
            """
            SELECT cb.* \n"
            "FROM chat_bot cb \n"
            "INNER JOIN chat_bot_phone_number cbpn ON cbpn.chat_bot_id = cb.chat_bot_id \n"
            "WHERE cbpn.trunk_phone_number = %s AND cbpn.status = 1 LIMIT 1"""
        )
        try:
            cursor.execute(query, (trunk_phone_number,))
        except Exception as e:
            # Fallback: attempt a direct lookup if mapping table differs
            logger.warning(
                f"Primary trunk phone number lookup failed, attempting fallback direct column (error={e})"
            )
            fallback_query = (
                "SELECT * FROM chat_bot WHERE trunk_phone_number = %s AND status = 1 LIMIT 1"
            )
            try:
                cursor.execute(fallback_query, (trunk_phone_number,))
            except Exception as inner_e:
                logger.error(
                    f"Fallback trunk phone number lookup failed: {inner_e}",
                    extra={"trunk_phone_number": trunk_phone_number},
                )
                cursor.close()
                connection_object.close()
                return None

        result = cursor.fetchone()
        cursor.close()
        connection_object.close()

        if result:
            # Provide compatibility defaults
            result.setdefault("namespace", result.get(
                "namespace", "default-namespace"))
            result.setdefault("index_name", result.get(
                "index_name", "default-index"))
            result.setdefault("is_presentation_agent", result.get(
                "is_presentation_agent", False))
        return result
    except Exception as e:
        logger.error(
            "Error getting chat bot by trunk phone number",
            extra={"error": str(e), "trunk_phone_number": trunk_phone_number},
        )
        return None


async def calculate_credits_used(total_tokens: int, tokens_per_credit: int = 70, minimum_credit: int = 20) -> int:
    """
    Calculate the number of credits to deduct based on total tokens used.
    Applies tiered logic and ensures a minimum credit deduction.
    """
    credits_deducted = total_tokens / tokens_per_credit
    if total_tokens > 1000:
        credits_deducted *= 1.5
    elif total_tokens > 500:
        credits_deducted *= 1.2
    # Ceiling division
    return max(int(-(-credits_deducted // 1)), minimum_credit)


async def check_customer_credits(customer_id: int, minimum_credits: int = 20) -> dict:
    """
    Check if customer has sufficient credits to continue.
    Returns a dict with has_credits (bool) and current_credits (int).
    """
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)
        query = """
            SELECT credits FROM customer_credit WHERE customer_id = %s
        """
        cursor.execute(query, (customer_id,))
        row = cursor.fetchone()
        current_credits = row['credits'] if row and 'credits' in row else 0
        has_credits = current_credits >= minimum_credits
        cursor.close()
        connection_object.close()
        return {
            "has_credits": has_credits,
            "current_credits": current_credits
        }
    except Exception as e:
        logger.error("Error checking customer credits", extra={
            "error": str(e),
            "customer_id": customer_id
        })
        return {"has_credits": False, "current_credits": 0}


async def deduct_customer_credits(customer_id: int, total_credits: int):
    """
    Handles credit calculation and deduction for a customer.
    Deducts total_credits from the customer's credits and updates total_spent.
    """
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)
        # Fetch current credits and total_spent
        select_query = """
            SELECT customer_credit_id, credits, total_spent FROM customer_credit WHERE customer_id = %s
        """
        cursor.execute(select_query, (customer_id,))
        row = cursor.fetchone()
        if not row:
            raise Exception(
                f"No customer_credit record found for customer_id {customer_id}")
        remaining_credits = row['credits'] - total_credits
        total_spent = (row['total_spent'] or 0) + total_credits
        # Update credits and total_spent
        update_query = """
            UPDATE customer_credit
            SET credits = %s, total_spent = %s
            WHERE customer_id = %s
        """
        cursor.execute(update_query, (remaining_credits,
                       total_spent, customer_id))
        connection_object.commit()
        cursor.close()
        connection_object.close()
    except Exception as e:
        logger.error("Error deducting customer credits", extra={
            "error": str(e),
            "customer_id": customer_id,
            "total_credits": total_credits
        })
        raise


async def get_agent_custom_prompt(knowledge_base_id: int):
    """
    Get agent custom prompt for a specific knowledge base.
    """
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)

        select_query = """
            SELECT chat_bot_feature_value 
            FROM chat_bot_related_feature 
            WHERE chat_bot_id = %s 
            AND chat_bot_feature_id = 1 
            AND status = 1
        """
        cursor.execute(select_query, (knowledge_base_id,))
        row = cursor.fetchone()

        cursor.close()
        connection_object.close()

        return row['chat_bot_feature_value'] if row else None

    except Exception as e:
        logger.error("Error getting agent custom prompt", extra={
            "error": str(e),
            "knowledge_base_id": knowledge_base_id
        })
        raise


async def get_realtime_information(customer_id: int):
    """Get realtime information for a specific customer."""
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)

        select_query = """
            SELECT info_key, info_value 
            FROM customer_realtime_information 
            WHERE customer_id = %s
        """
        cursor.execute(select_query, (customer_id,))
        results = cursor.fetchall()

        cursor.close()
        connection_object.close()

        return results

    except Exception as e:
        logger.error("Error retrieving customer realtime information", extra={
            "error": str(e),
            "customer_id": customer_id
        })
        raise


async def upsert_customer_realtime_information(customer_id: int, key: str, value: str) -> bool:
    """Insert or update a customer's realtime information key/value."""
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)

        # Try update first
        update_query = """
            UPDATE customer_realtime_information
            SET info_value = %s
            WHERE customer_id = %s AND info_key = %s
        """
        cursor.execute(update_query, (value, customer_id, key))
        if cursor.rowcount == 0:
            insert_query = """
                INSERT INTO customer_realtime_information (customer_id, info_key, info_value)
                VALUES (%s, %s, %s)
            """
            cursor.execute(insert_query, (customer_id, key, value))

        connection_object.commit()
        cursor.close()
        connection_object.close()
        return True
    except Exception as e:
        logger.error("Error upserting customer realtime information", extra={
            "error": str(e),
            "customer_id": customer_id,
            "key": key,
        })
        try:
            connection_object.rollback()
        except Exception:
            pass
        return False

async def log_chat_transaction(data: dict):
    """Log a chat transaction to the database."""
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)

        chat_data = {
            'conversation_id': data['conversationId'],
            'customer_id': data.get('customerId'),
            'user_session_id': data.get('userSessionId'),
            'chat': data['message'],
            'character_count': len(data['message']),
            'credits': data.get('credits', 0),
            'is_question': 1 if data['isQuestion'] else 0,
            'chat_type': data.get('chatType'),
            'request_id': data.get('requestId'),
            'animation': data.get('animation'),
            'expression': data.get('expression'),
            'status': True,
            'created_by': data.get('customerId'),
            'updated_by': data.get('customerId'),
        }

        insert_query = """
            INSERT INTO chat (
                conversation_id, customer_id, user_session_id, chat, character_count,
                credits, is_question, chat_type, request_id, animation, expression,
                status, created_by, updated_by
            ) VALUES (
                %(conversation_id)s, %(customer_id)s, %(user_session_id)s, %(chat)s, %(character_count)s,
                %(credits)s, %(is_question)s, %(chat_type)s, %(request_id)s, %(animation)s, %(expression)s,
                %(status)s, %(created_by)s, %(updated_by)s
            )
        """

        cursor.execute(insert_query, chat_data)
        connection_object.commit()

        chat_id = cursor.lastrowid

        # Fetch the created record
        select_query = "SELECT * FROM chat WHERE chat_id = %s"
        cursor.execute(select_query, (chat_id,))
        result = cursor.fetchone()
        cursor.close()
        connection_object.close()

        return result

    except Exception as e:
        logger.error("Error logging chat transaction to database", extra={
            "error": str(e),
            "conversation_id": data.get('conversationId'),
            "customer_id": data.get('customerId', 'N/A'),
            "message_length": len(data.get('message', ''))
        })
        return None

async def fetch_customer_mcp_server_urls(customer_id: int) -> list[str]:
    """Fetch MCP server URLs configured for a given customer."""
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)
        query = """
            SELECT mcp_server_url
            FROM composio_mcp_tool_integration
            WHERE customer_id = %s AND is_enabled = 1
        """
        try:
            cursor.execute(query, (customer_id,))
            rows = cursor.fetchall() or []
            urls = [row.get('mcp_server_url')
                    for row in rows if row.get('mcp_server_url')]
        except Exception:
            fallback_query = """
                SELECT url as mcp_server_url
                FROM composio_mcp_tool_integration
                WHERE customer_id = %s AND status = 1
            """
            cursor.execute(fallback_query, (customer_id,))
            rows = cursor.fetchall() or []
            urls = [row.get('mcp_server_url')
                    for row in rows if row.get('mcp_server_url')]
        finally:
            cursor.close()
            connection_object.close()
        return urls
    except Exception as e:
        logger.error("Error fetching customer MCP server URLs", extra={
            "error": str(e),
            "customer_id": customer_id,
        })
        return []

async def fetch_metadata_by_trunk_phone_number(trunk_phone_number: str) -> dict:
    """Fetch minimal metadata (single DB query) using trunk phone number.

    Returns dict with keys: conversationId, customerId, userSessionId, knowledgebaseId, environment.
    Falls back to safe defaults if not found. Adds raw chatbot row under key 'chatbot'.
    """
    try:
        connection_object = connection_pool.get_connection()
        cursor = connection_object.cursor(dictionary=True)
        query = (
            """
            SELECT
                cpnm.customer_id,
                cti.sip_trunk_id,
                cti.knowledge_base_id,
                lm.llm_environment,
                lm.llm_model,
                v.voice_setup
            FROM
                customer_phone_number_mapping AS cpnm
            JOIN
                customer_twilio_information AS cti ON cti.customer_phone_number_mapping_id = cpnm.customer_phone_number_mapping_id
            JOIN
                llm_model AS lm ON lm.llm_model_id = cti.llm_model_id
            JOIN
                voice AS v ON v.voice_id = cti.voice_id
            WHERE
                cpnm.phone_number = %s
            LIMIT 1
            """
        )
        cursor.execute(query, (trunk_phone_number,))
        row = cursor.fetchone()
        cursor.close()
        connection_object.close()
        if not row:
            return None
        meta = {
            "customerId": row.get("customer_id"),
            "sipTrunkId":row.get("sip_trunk_id"),
            "knowledgebaseId": row.get("knowledge_base_id"),
            "environment": row.get("llm_environment"),
            "voice": row.get("voice_setup"),
            "llmName": row.get("llm_model"),
        }
        return meta
    except Exception as e:
        logger.error("Error fetching metadata by trunk phone number", extra={
                     "error": str(e), "trunk_phone_number": trunk_phone_number})
        return None
