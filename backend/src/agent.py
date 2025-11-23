import logging
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any

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

logger = logging.getLogger("agent")

load_dotenv(".env.local")

WELLNESS_LOG_FILE = "wellness_log.json"


@dataclass
class WellnessState:
    """Tracks the current wellness check-in state"""
    mood: Optional[str] = None
    energy_level: Optional[str] = None
    stress_factors: Optional[str] = None
    objectives: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    date: Optional[str] = None
    
    def is_complete(self) -> bool:
        """Check if the check-in has enough information"""
        return all([
            self.mood is not None,
            len(self.objectives) > 0
        ])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


def load_wellness_history() -> List[Dict[str, Any]]:
    """Load previous wellness check-ins from JSON file"""
    if not os.path.exists(WELLNESS_LOG_FILE):
        return []
    
    try:
        with open(WELLNESS_LOG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading wellness history: {e}")
        return []


def save_wellness_entry(entry: Dict[str, Any]) -> bool:
    """Save a wellness check-in entry to JSON file"""
    try:
        history = load_wellness_history()
        history.append(entry)
        
        with open(WELLNESS_LOG_FILE, "w") as f:
            json.dump(history, f, indent=2)
        
        logger.info(f"Wellness entry saved: {entry}")
        return True
    except Exception as e:
        logger.error(f"Error saving wellness entry: {e}")
        return False


def get_last_checkin_summary() -> Optional[str]:
    """Get a summary of the last check-in for context"""
    history = load_wellness_history()
    if not history:
        return None
    
    last_entry = history[-1]
    return f"Last time on {last_entry.get('date', 'a previous day')}, you mentioned feeling {last_entry.get('mood', 'N/A')} with energy level of {last_entry.get('energy_level', 'N/A')}."


class WellnessCompanion(Agent):
    def __init__(self) -> None:
        # Load previous check-in for context
        last_checkin = get_last_checkin_summary()
        context_note = f"\n\nPrevious session context: {last_checkin}" if last_checkin else "\n\nThis appears to be the user's first check-in with you."
        
        super().__init__(
            instructions=f"""You are a supportive and grounded health & wellness companion. Your role is to conduct brief daily check-ins to help users reflect on their wellbeing and set intentions.

You are NOT a medical professional. You do not diagnose, prescribe, or provide medical advice. You offer supportive listening and simple, practical suggestions for wellbeing.

Your conversation flow:
1. Greet the user warmly and ask about their mood and energy today
   - "How are you feeling today?"
   - "What's your energy level like?"
   - "Is anything stressing you out right now?"

2. Ask about their intentions or objectives for the day
   - "What are 1 to 3 things you'd like to get done today?"
   - "Is there anything you want to do for yourself, like rest, exercise, or a hobby?"

3. Offer simple, realistic advice or reflections
   - Keep suggestions small and actionable
   - Examples: break large goals into smaller steps, take short breaks, go for a 5-minute walk
   - Be encouraging but realistic

4. Close with a brief recap
   - Summarize their mood and main objectives
   - Ask: "Does this sound right?"
   - Once confirmed, save the check-in

Keep responses conversational, warm, and natural. Use voice-friendly language without complex formatting or emojis.{context_note}""",
        )
        self.wellness = WellnessState()
        self.wellness.date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @function_tool
    async def update_wellness_checkin(
        self,
        context: RunContext,
        mood: Optional[str] = None,
        energy_level: Optional[str] = None,
        stress_factors: Optional[str] = None,
        objectives: Optional[str] = None
    ):
        """Record wellness check-in information as the user shares it.
        
        Use this tool to capture what the user tells you about their wellbeing and goals.
        
        Args:
            mood: User's self-reported mood or emotional state
            energy_level: User's energy level (e.g., low, medium, high, tired, energized)
            stress_factors: What's causing stress or concern (optional)
            objectives: Goals or intentions for the day (can be comma-separated for multiple objectives)
        """
        
        if mood:
            self.wellness.mood = mood
        if energy_level:
            self.wellness.energy_level = energy_level
        if stress_factors:
            self.wellness.stress_factors = stress_factors
        if objectives:
            # Parse objectives (handle comma-separated or single objective)
            new_objectives = [obj.strip() for obj in objectives.split(",") if obj.strip()]
            self.wellness.objectives.extend(new_objectives)
        
        # Build current status summary
        status_parts = []
        if self.wellness.mood:
            status_parts.append(f"Mood: {self.wellness.mood}")
        if self.wellness.energy_level:
            status_parts.append(f"Energy: {self.wellness.energy_level}")
        if self.wellness.stress_factors:
            status_parts.append(f"Stress: {self.wellness.stress_factors}")
        if self.wellness.objectives:
            status_parts.append(f"Objectives: {', '.join(self.wellness.objectives)}")
        
        current_status = " | ".join(status_parts) if status_parts else "No information recorded yet"
        
        logger.info(f"Wellness check-in updated: {current_status}")
        
        return f"Recorded. Current check-in: {current_status}"

    @function_tool
    async def save_wellness_checkin(self, context: RunContext, summary: str):
        """Save the completed wellness check-in to the JSON log file.
        
        Use this tool ONLY after you have:
        1. Gathered mood and objectives
        2. Provided your recap
        3. Received confirmation from the user that the recap is correct
        
        Args:
            summary: A brief one-sentence summary of the check-in from your perspective
        """
        
        if not self.wellness.is_complete():
            missing = []
            if not self.wellness.mood:
                missing.append("mood")
            if len(self.wellness.objectives) == 0:
                missing.append("at least one objective")
            
            return f"Cannot save check-in yet. Still need: {', '.join(missing)}"
        
        # Add the summary
        self.wellness.summary = summary
        
        # Convert to dict and save
        entry = self.wellness.to_dict()
        
        if save_wellness_entry(entry):
            objectives_list = ', '.join(self.wellness.objectives)
            return f"Your check-in has been saved! Wishing you a great day working on: {objectives_list}"
        else:
            return "There was an issue saving your check-in, but I've noted everything we discussed."


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
        agent=WellnessCompanion(),
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
