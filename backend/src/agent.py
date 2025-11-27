# import logging
# import json
# from datetime import datetime
# from pathlib import Path

# from dotenv import load_dotenv
# from livekit.agents import (
#     Agent,
#     AgentSession,
#     JobContext,
#     JobProcess,
#     MetricsCollectedEvent,
#     RoomInputOptions,
#     WorkerOptions,
#     cli,
#     metrics,
#     tokenize,
#     function_tool,
#     RunContext,
# )
# from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
# from livekit.plugins.turn_detector.multilingual import MultilingualModel

# logger = logging.getLogger("agent")

# load_dotenv(".env.local")

# # JSON file path - in src folder
# JSON_PATH = Path(__file__).parent / "fraud_cases.json"


# # ------------------------ JSON HELPERS ------------------------ #

# def _read_cases():
#     """Read all fraud cases from JSON file."""
#     with open(JSON_PATH, "r", encoding="utf-8") as f:
#         return json.load(f)


# def _write_cases(cases):
#     """Write all fraud cases to JSON file."""
#     with open(JSON_PATH, "w", encoding="utf-8") as f:
#         json.dump(cases, f, indent=2)


# def _normalize_username(name: str) -> str:
#     """Normalize username for comparison."""
#     return name.lower().replace(" ", "").replace("-", "")


# def get_fraud_case_by_username(username: str):
#     """
#     Retrieve a pending fraud case for a specific user.

#     Args:
#         username: The user's name

#     Returns:
#         Dictionary containing fraud case details or None if not found
#     """
#     cases = _read_cases()
#     normalized_input = _normalize_username(username)

#     for case in cases:
#         if case.get("userName") and case.get("caseStatus") == "pending_review":
#             normalized_stored = _normalize_username(case["userName"])
#             if normalized_stored == normalized_input:
#                 return case

#     return None


# def verify_security_identifier(username: str, identifier: str) -> bool:
#     """
#     Verify the security identifier for a user.

#     Args:
#         username: The user's name
#         identifier: The security identifier to verify

#     Returns:
#         True if identifier matches, False otherwise
#     """
#     case = get_fraud_case_by_username(username)
#     if case:
#         return case["securityIdentifier"].strip() == identifier.strip()
#     return False


# def verify_security_answer(username: str, answer: str) -> bool:
#     """
#     Verify the security question answer for a user.

#     Args:
#         username: The user's name
#         answer: The security answer to verify

#     Returns:
#         True if answer matches (case-insensitive), False otherwise
#     """
#     case = get_fraud_case_by_username(username)
#     if case and case.get("securityAnswer"):
#         return case["securityAnswer"].lower().strip() == answer.lower().strip()
#     return False


# def update_fraud_case_status(username: str, status: str, outcome: str) -> bool:
#     """
#     Update the fraud case status and outcome for a user.

#     Args:
#         username: The user's (spoken) name
#         status: New status (e.g., 'confirmed_safe', 'confirmed_fraud', 'verification_failed')
#         outcome: Description of the outcome

#     Returns:
#         True if update successful, False otherwise
#     """
#     try:
#         cases = _read_cases()
#         updated = False

#         normalized_input = _normalize_username(username)

#         for case in cases:
#             if case.get("caseStatus") == "pending_review":
#                 normalized_stored = _normalize_username(case["userName"])
#                 if normalized_stored == normalized_input:
#                     case["caseStatus"] = status
#                     case["outcome"] = outcome
#                     case["lastUpdated"] = datetime.now().isoformat()
#                     updated = True
#                     break

#         if updated:
#             _write_cases(cases)
#             logger.info(f"Updated fraud case for {username}: {status} - {outcome}")
#             return True
#         else:
#             logger.warning(f"No pending fraud case found for {username}")
#             return False
#     except Exception as e:
#         logger.error(f"Error updating fraud case: {e}")
#         return False


# # ------------------------ ASSISTANT CLASS ------------------------ #

# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions="""You are Amit, a fraud detection representative from UBI (Union Bank of India) fraud prevention department. 
# The user is interacting with you via voice.

# Your role is to:
# 1. Introduce yourself professionally as Amit calling from UBI (Union Bank of India) fraud department.
# 2. Verify the customer's identity using their username and security identifier.
# 3. Ask the security question from their file to confirm their identity.
# 4. Explain the suspicious transaction clearly and calmly.
# 5. Ask if they made the transaction (yes or no).
# 6. Take appropriate action based on their response.

# CALL FLOW:
# - Start by greeting them and introducing yourself as Amit from UBI fraud department.
# - Ask for their name (username).
# - Use load_fraud_case tool to get their fraud case details.
# - Ask for their security identifier to verify identity.
# - Use verify_identifier tool to check it.
# - If verification fails, politely end the call using mark_verification_failed tool.
# - If verified, ask the security question from their case.
# - Use verify_security_answer tool to check their answer.
# - If answer is wrong, politely end the call using mark_verification_failed tool.
# - If answer is correct, read out the suspicious transaction details.
# - Ask clearly: "Did you make this transaction?"
# - Based on their yes/no answer:
#   * If YES: Use mark_transaction_safe tool.
#   * If NO: Use mark_transaction_fraudulent tool.
# - Confirm the action taken and thank them.

# Keep responses concise, professional, and reassuring.
# Never ask for full card numbers, PINs, or passwords.
# Use the provided tools to load cases and update statuses.""",
#         )

#         # Store current fraud case context
#         self.current_case = None
#         self.current_username = None  # canonical username from JSON

#     # ------------------------ TOOLS ------------------------ #

#     @function_tool
#     async def load_fraud_case(self, context: RunContext, username: str):
#         """Load the pending fraud case for a specific user.

#         This tool retrieves fraud case details from the database for the given username.
#         Use this after the user provides their name.

#         Args:
#             username: The customer's spoken name
#         """
#         logger.info(f"Loading fraud case for username: {username}")

#         case = get_fraud_case_by_username(username)

#         if case:
#             # store canonical username from the file
#             self.current_case = case
#             self.current_username = case["userName"]
#             logger.info(f"Loaded case: {case}")

#             return f"""Fraud case loaded for {case['userName']}.
# Card ending: {case['cardEnding']}
# Transaction: ₹{case['transactionAmount']} at {case['transactionName']}
# Category: {case['transactionCategory']}
# Location: {case['transactionLocation']}
# Time: {case['transactionTime']}
# Source: {case['transactionSource']}
# Security Question: {case['securityQuestion']}

# Now verify their security identifier before proceeding."""
#         else:
#             self.current_case = None
#             self.current_username = None
#             logger.warning(f"No pending fraud case found for {username}")
#             return f"No pending fraud alert found for {username}. This call may be in error."

#     @function_tool
#     async def verify_identifier(self, context: RunContext, identifier: str):
#         """Verify the customer's security identifier.

#         Use this tool after the user provides their security identifier to verify their identity.

#         Args:
#             identifier: The security identifier provided by the customer
#         """
#         if not self.current_username:
#             return "Error: No fraud case loaded yet. Ask for username first."

#         logger.info(f"Verifying identifier for {self.current_username}: {identifier}")

#         is_valid = verify_security_identifier(self.current_username, identifier)

#         if is_valid:
#             return "Security identifier verified successfully. Now ask the security question."
#         else:
#             return "Security identifier does not match. Identity verification failed."

#     @function_tool
#     async def verify_security_answer(self, context: RunContext, answer: str):
#         """Verify the customer's answer to the security question.

#         Use this tool after the customer answers the security question.

#         Args:
#             answer: The customer's answer to the security question
#         """
#         if not self.current_username or not self.current_case:
#             return "Error: No fraud case loaded yet."

#         logger.info(f"Verifying security answer for {self.current_username}")

#         is_correct = verify_security_answer(self.current_username, answer)

#         if is_correct:
#             return "Security answer verified. Identity confirmed. Now read out the transaction details and ask if they made the purchase."
#         else:
#             return "Security answer incorrect. Identity verification failed."

#     @function_tool
#     async def mark_transaction_safe(self, context: RunContext):
#         """Mark the transaction as safe (customer confirmed they made it).

#         Use this tool when the customer confirms YES, they made the transaction.
#         """
#         if not self.current_username:
#             return "Error: No fraud case loaded."

#         logger.info(f"Marking transaction as safe for {self.current_username}")

#         outcome = "Customer confirmed transaction as legitimate."
#         success = update_fraud_case_status(
#             self.current_username,
#             "confirmed_safe",
#             outcome,
#         )

#         if success:
#             return "Transaction marked as safe. No further action needed. Thank the customer and end the call."
#         else:
#             return "Error updating case status. Inform the customer that the case could not be updated and suggest contacting the bank."

#     @function_tool
#     async def mark_transaction_fraudulent(self, context: RunContext):
#         """Mark the transaction as fraudulent (customer denied making it).

#         Use this tool when the customer confirms NO, they did NOT make the transaction.
#         """
#         if not self.current_username or not self.current_case:
#             return "Error: No fraud case loaded."

#         logger.info(f"Marking transaction as fraudulent for {self.current_username}")

#         outcome = (
#             f"Customer denied transaction. Card ending {self.current_case['cardEnding']} "
#             f"has been blocked. Dispute case opened."
#         )
#         success = update_fraud_case_status(
#             self.current_username,
#             "confirmed_fraud",
#             outcome,
#         )

#         if success:
#             return "Transaction marked as fraudulent. Card has been blocked and a dispute case has been opened. Inform the customer and thank them for reporting this."
#         else:
#             return "Error updating case status. Inform the customer that the case could not be updated and suggest contacting the bank."

#     @function_tool
#     async def mark_verification_failed(self, context: RunContext):
#         """Mark the case as verification failed.

#         Use this tool when identity verification fails (wrong identifier or security answer).
#         """
#         if not self.current_username:
#             return "No case to mark."

#         logger.info(f"Marking verification failed for {self.current_username}")

#         outcome = "Identity verification failed during fraud alert call."
#         success = update_fraud_case_status(
#             self.current_username,
#             "verification_failed",
#             outcome,
#         )

#         if success:
#             return "Verification marked as failed. Politely end the call and suggest they contact the bank directly."
#         else:
#             return "Error updating case status. Politely suggest they contact the bank directly."


# # ------------------------ LIVEKIT ENTRYPOINT ------------------------ #


# def prewarm(proc: JobProcess):
#     proc.userdata["vad"] = silero.VAD.load()


# async def entrypoint(ctx: JobContext):
#     # Logging setup
#     ctx.log_context_fields = {
#         "room": ctx.room.name,
#     }

#     session = AgentSession(
#         stt=deepgram.STT(model="nova-3"),
#         llm=google.LLM(
#             model="gemini-2.5-flash",
#         ),
#         tts=murf.TTS(
#             voice="en-US-matthew",
#             style="Conversation",
#             tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
#             text_pacing=True,
#         ),
#         turn_detection=MultilingualModel(),
#         vad=ctx.proc.userdata["vad"],
#         preemptive_generation=True,
#     )

#     usage_collector = metrics.UsageCollector()

#     @session.on("metrics_collected")
#     def _on_metrics_collected(ev: MetricsCollectedEvent):
#         metrics.log_metrics(ev.metrics)
#         usage_collector.collect(ev.metrics)

#     async def log_usage():
#         summary = usage_collector.get_summary()
#         logger.info(f"Usage: {summary}")

#     ctx.add_shutdown_callback(log_usage)

#     await session.start(
#         agent=Assistant(),
#         room=ctx.room,
#         room_input_options=RoomInputOptions(
#             noise_cancellation=noise_cancellation.BVC(),
#         ),
#     )

#     await ctx.connect()


# if __name__ == "__main__":
#     cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))


import logging
import json
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    tokenize,
    function_tool,
    RunContext,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# JSON file path - in src folder
JSON_PATH = Path(__file__).parent / "fraud_cases.json"


# ------------------------ JSON HELPERS ------------------------ #

def _read_cases():
    """Read all fraud cases from JSON file safely."""
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading fraud cases JSON: {e}")
        return []


def _write_cases(cases):
    """Write all fraud cases to JSON file."""
    try:
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(cases, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing fraud cases JSON: {e}")


def _normalize_username(name: str) -> str:
    """Normalize username for comparison."""
    if not isinstance(name, str):
        return ""
    return name.lower().replace(" ", "").replace("-", "")


def _fuzzy_match(a: str, b: str) -> float:
    """Return similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def get_fraud_case_by_username(username: str):
    """
    Retrieve a pending fraud case for a specific user, with robust
    recognition of spoken username (handles minor variations).

    Args:
        username: The user's spoken name

    Returns:
        Dictionary containing fraud case details or None if not found
    """
    cases = _read_cases()
    spoken = _normalize_username(username)

    for case in cases:
        if case.get("caseStatus") != "pending_review" or not case.get("userName"):
            continue

        stored = _normalize_username(case["userName"])

        # 1. Exact match
        if spoken == stored:
            return case

        # 2. Partial match based on first few characters (first name style)
        if spoken and stored.startswith(spoken[:4]):
            return case

        # 3. Fuzzy similarity match
        if _fuzzy_match(spoken, stored) > 0.75:
            return case

    return None


def verify_security_identifier(username: str, identifier: str) -> bool:
    """
    Verify the security identifier for a user.

    Args:
        username: The user's name (canonical username from JSON)
        identifier: The security identifier to verify

    Returns:
        True if identifier matches, False otherwise
    """
    case = get_fraud_case_by_username(username)
    if case and case.get("securityIdentifier") is not None:
        return case["securityIdentifier"].strip() == identifier.strip()
    return False


def verify_security_answer(username: str, answer: str) -> bool:
    """
    Verify the security question answer for a user.

    Args:
        username: The user's name (canonical username from JSON)
        answer: The security answer to verify

    Returns:
        True if answer matches (case-insensitive), False otherwise
    """
    case = get_fraud_case_by_username(username)
    if case and case.get("securityAnswer"):
        return case["securityAnswer"].lower().strip() == answer.lower().strip()
    return False


def update_fraud_case_status(username: str, status: str, outcome: str) -> bool:
    """
    Update the fraud case status and outcome for a user.

    Args:
        username: The user's (spoken) name
        status: New status ('confirmed_safe', 'confirmed_fraud', 'verification_failed')
        outcome: Description of the outcome

    Returns:
        True if update successful, False otherwise
    """
    try:
        cases = _read_cases()
        spoken = _normalize_username(username)
        updated = False

        for case in cases:
            if case.get("caseStatus") != "pending_review" or not case.get("userName"):
                continue

            stored = _normalize_username(case["userName"])

            # Reuse same matching logic so update hits the right case
            if (
                spoken == stored
                or (spoken and stored.startswith(spoken[:4]))
                or _fuzzy_match(spoken, stored) > 0.75
            ):
                case["caseStatus"] = status
                case["outcome"] = outcome
                case["lastUpdated"] = datetime.now().isoformat()
                updated = True
                break

        if updated:
            _write_cases(cases)
            logger.info(f"Updated fraud case for {username}: {status} - {outcome}")
            return True
        else:
            logger.warning(f"No pending fraud case found for {username} to update")
            return False

    except Exception as e:
        logger.error(f"Error updating fraud case: {e}")
        return False


# ------------------------ ASSISTANT CLASS ------------------------ #

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Amit, a fraud detection representative from UBI (Union Bank of India) fraud prevention department. 
The user is interacting with you via voice.

Your role is to:
1. Introduce yourself professionally as Amit calling from UBI (Union Bank of India) fraud department.
2. Verify the customer's identity using their username and security identifier.
3. Ask the security question from their file to confirm their identity.
4. Explain the suspicious transaction clearly and calmly.
5. Ask if they made the transaction (yes or no).
6. Take appropriate action based on their response.

CALL FLOW:
- Start by greeting them and introducing yourself as Amit from UBI fraud department.
- Ask for their name (username).
- Use load_fraud_case tool to get their fraud case details.
- Ask for their security identifier to verify identity.
- Use verify_identifier tool to check it.
- If verification fails, politely end the call using mark_verification_failed tool.
- If verified, ask the security question from their case.
- Use verify_security_answer tool to check their answer.
- If answer is wrong, politely end the call using mark_verification_failed tool.
- If answer is correct, read out the suspicious transaction details.
- Ask clearly: "Did you make this transaction?"
- Based on their yes/no answer:
  * If YES: Use mark_transaction_safe tool.
  * If NO: Use mark_transaction_fraudulent tool.
- Confirm the action taken and thank them.

Keep responses concise, professional, and reassuring.
Never ask for full card numbers, PINs, or passwords.
Use the provided tools to load cases and update statuses.""",
        )

        # Store current fraud case context
        self.current_case = None
        self.current_username = None  # canonical username from JSON

    # ------------------------ TOOLS ------------------------ #

    @function_tool
    async def load_fraud_case(self, context: RunContext, username: str):
        """Load the pending fraud case for a specific user.

        This tool retrieves fraud case details from the database for the given username.
        Use this after the user provides their name.

        Args:
            username: The customer's spoken name
        """
        logger.info(f"Loading fraud case for username: {username}")

        case = get_fraud_case_by_username(username)

        if case:
            # Store canonical username from the file
            self.current_case = case
            self.current_username = case["userName"]
            logger.info(f"Loaded case: {case}")

            return (
                f"Fraud case loaded for {case['userName']}.\n"
                f"Card ending: {case['cardEnding']}\n"
                f"Transaction: ₹{case['transactionAmount']} at {case['transactionName']}\n"
                f"Category: {case['transactionCategory']}\n"
                f"Location: {case['transactionLocation']}\n"
                f"Time: {case['transactionTime']}\n"
                f"Source: {case['transactionSource']}\n"
                f"Security Question: {case['securityQuestion']}\n\n"
                "Now verify their security identifier before proceeding."
            )
        else:
            self.current_case = None
            self.current_username = None
            logger.warning(f"No pending fraud case found for {username}")
            return f"No pending fraud alert found for {username}. This call may be in error."

    @function_tool
    async def verify_identifier(self, context: RunContext, identifier: str):
        """Verify the customer's security identifier.

        Use this tool after the user provides their security identifier to verify their identity.

        Args:
            identifier: The security identifier provided by the customer
        """
        if not self.current_username:
            return "Error: No fraud case loaded yet. Ask for username first."

        logger.info(f"Verifying identifier for {self.current_username}: {identifier}")

        is_valid = verify_security_identifier(self.current_username, identifier)

        if is_valid:
            return "Security identifier verified successfully. Now ask the security question."
        else:
            return "Security identifier does not match. Identity verification failed."

    @function_tool
    async def verify_security_answer(self, context: RunContext, answer: str):
        """Verify the customer's answer to the security question.

        Use this tool after the customer answers the security question.

        Args:
            answer: The customer's answer to the security question
        """
        if not self.current_username or not self.current_case:
            return "Error: No fraud case loaded yet."

        logger.info(f"Verifying security answer for {self.current_username}")

        is_correct = verify_security_answer(self.current_username, answer)

        if is_correct:
            return (
                "Security answer verified. Identity confirmed. Now read out the "
                "transaction details and ask if they made the purchase."
            )
        else:
            return "Security answer incorrect. Identity verification failed."

    @function_tool
    async def mark_transaction_safe(self, context: RunContext):
        """Mark the transaction as safe (customer confirmed they made it).

        Use this tool when the customer confirms YES, they made the transaction.
        """
        if not self.current_username:
            return "Error: No fraud case loaded."

        logger.info(f"Marking transaction as safe for {self.current_username}")

        outcome = "Customer confirmed transaction as legitimate."
        success = update_fraud_case_status(
            self.current_username,
            "confirmed_safe",
            outcome,
        )

        if success:
            return (
                "Transaction marked as safe. No further action is needed. "
                "Thank the customer and end the call."
            )
        else:
            return (
                "Error updating case status. Inform the customer that the case could "
                "not be updated and suggest contacting the bank."
            )

    @function_tool
    async def mark_transaction_fraudulent(self, context: RunContext):
        """Mark the transaction as fraudulent (customer denied making it).

        Use this tool when the customer confirms NO, they did NOT make the transaction.
        """
        if not self.current_username or not self.current_case:
            return "Error: No fraud case loaded."

        logger.info(f"Marking transaction as fraudulent for {self.current_username}")

        outcome = (
            f"Customer denied transaction. Card ending {self.current_case['cardEnding']} "
            f"has been blocked. Dispute case opened."
        )
        success = update_fraud_case_status(
            self.current_username,
            "confirmed_fraud",
            outcome,
        )

        if success:
            return (
                "Transaction marked as fraudulent. The card has been blocked and a "
                "dispute case has been opened. Inform the customer and thank them "
                "for reporting this."
            )
        else:
            return (
                "Error updating case status. Inform the customer that the case could "
                "not be updated and suggest contacting the bank."
            )

    @function_tool
    async def mark_verification_failed(self, context: RunContext):
        """Mark the case as verification failed.

        Use this tool when identity verification fails (wrong identifier or security answer)."""
        if not self.current_username:
            return "No case to mark."

        logger.info(f"Marking verification failed for {self.current_username}")

        outcome = "Identity verification failed during fraud alert call."
        success = update_fraud_case_status(
            self.current_username,
            "verification_failed",
            outcome,
        )

        if success:
            return (
                "Verification marked as failed. Politely end the call and suggest "
                "they contact the bank directly."
            )
        else:
            return (
                "Error updating case status. Politely suggest they contact the bank directly."
            )


# ------------------------ LIVEKIT ENTRYPOINT ------------------------ #


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(
            model="gemini-2.5-flash",
        ),
        tts=murf.TTS(
            voice="en-US-matthew",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
