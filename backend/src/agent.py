import logging
from datetime import datetime

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
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Import database functions
from database import (
    init_database,
    get_fraud_case_by_username,
    verify_security_identifier,
    verify_security_answer,
    update_fraud_case_status
)

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Initialize database on module load
init_database()



class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Amit, a fraud detection representative from UBI Bank's (Union Bank of India) fraud prevention department. 
            The user is interacting with you via voice.
            
            Your role is to:
            1. Introduce yourself professionally as Amit calling from UBI Bank's fraud department
            2. Verify the customer's identity using their username and security identifier
            3. Ask the security question from their file to confirm their identity
            4. Explain the suspicious transaction clearly and calmly
            5. Ask if they made the transaction (yes or no)
            6. Take appropriate action based on their response
            
            CALL FLOW:
            - Start by greeting them and introducing yourself as Amit from UBI Bank fraud department
            - Ask for their name (username)
            - Use load_fraud_case tool to get their fraud case details
            - Ask for their security identifier to verify identity
            - Use verify_identifier tool to check it
            - If verification fails, politely end the call using mark_verification_failed tool
            - If verified, ask the security question from their case
            - Use verify_security_answer tool to check their answer
            - If answer is wrong, politely end the call using mark_verification_failed tool
            - If answer is correct, read out the suspicious transaction details
            - Ask clearly: "Did you make this transaction?"
            - Based on their yes/no answer:
              * If YES: Use mark_transaction_safe tool
              * If NO: Use mark_transaction_fraudulent tool
            - Confirm the action taken and thank them
            
            Keep responses concise, professional, and reassuring.
            Never ask for full card numbers, PINs, or passwords.
            Use the provided tools to load cases and update statuses.""",
        )
        
        # Store current fraud case context
        self.current_case = None
        self.current_username = None

    @function_tool
    async def load_fraud_case(self, context: RunContext, username: str):
        """Load the pending fraud case for a specific user.
        
        This tool retrieves fraud case details from the database for the given username.
        Use this after the user provides their name.
        
        Args:
            username: The customer's name
        """
        logger.info(f"Loading fraud case for username: {username}")
        
        case = get_fraud_case_by_username(username)
        
        if case:
            self.current_case = case
            # Store the actual username from database, not user input
            self.current_username = case['userName']
            logger.info(f"Loaded case: {case}")
            
            return f"""Fraud case loaded for {username}.
Card ending: {case['cardEnding']}
Transaction: ${case['transactionAmount']} at {case['transactionName']}
Category: {case['transactionCategory']}
Location: {case['transactionLocation']}
Time: {case['transactionTime']}
Source: {case['transactionSource']}
Security Question: {case['securityQuestion']}

Now verify their security identifier before proceeding."""
        else:
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
            return "Security answer verified. Identity confirmed. Now read out the transaction details and ask if they made the purchase."
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
            outcome
        )
        
        if success:
            return f"Transaction marked as safe. No further action needed. Thank the customer and end the call."
        else:
            return "Error updating case status."

    @function_tool
    async def mark_transaction_fraudulent(self, context: RunContext):
        """Mark the transaction as fraudulent (customer denied making it).
        
        Use this tool when the customer confirms NO, they did NOT make the transaction.
        """
        if not self.current_username:
            return "Error: No fraud case loaded."
        
        logger.info(f"Marking transaction as fraudulent for {self.current_username}")
        
        outcome = f"Customer denied transaction. Card ending {self.current_case['cardEnding']} has been blocked. Dispute case opened."
        success = update_fraud_case_status(
            self.current_username,
            "confirmed_fraud",
            outcome
        )
        
        if success:
            return f"Transaction marked as fraudulent. Card has been blocked and dispute opened. Inform the customer and thank them for reporting this."
        else:
            return "Error updating case status."

    @function_tool
    async def mark_verification_failed(self, context: RunContext):
        """Mark the case as verification failed.
        
        Use this tool when identity verification fails (wrong identifier or security answer).
        """
        if not self.current_username:
            return "No case to mark."
        
        logger.info(f"Marking verification failed for {self.current_username}")
        
        outcome = "Identity verification failed during fraud alert call."
        success = update_fraud_case_status(
            self.current_username,
            "verification_failed",
            outcome
        )
        
        if success:
            return "Verification marked as failed. Politely end the call and suggest they contact the bank directly."
        else:
            return "Error updating case status."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt=deepgram.STT(model="nova-3"),
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm=google.LLM(
                model="gemini-2.5-flash",
            ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts=murf.TTS(
                voice="en-US-matthew", 
                style="Conversation",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True
            ),
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
    )

    # To use a realtime model instead of a voice pipeline, use the following session setup instead.
    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
    # 1. Install livekit-agents[openai]
    # 2. Set OPENAI_API_KEY in .env.local
    # 3. Add `from livekit.plugins import openai` to the top of this file
    # 4. Use the following session setup instead of the version above
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel(voice="marin")
    # )

    # Metrics collection, to measure pipeline performance
    # For more information, see https://docs.livekit.io/agents/build/metrics/
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # # Add a virtual avatar to the session, if desired
    # # For other providers, see https://docs.livekit.io/agents/models/avatar/
    # avatar = hedra.AvatarSession(
    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
    # )
    # # Start the avatar and wait for it to join
    # await avatar.start(session, room=ctx.room)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))