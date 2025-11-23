import logging
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

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


@dataclass
class OrderState:
    """Tracks the current coffee order state"""
    drinkType: Optional[str] = None
    size: Optional[str] = None
    milk: Optional[str] = None
    extras: list[str] = field(default_factory=list)
    name: Optional[str] = None
    
    def is_complete(self) -> bool:
        """Check if all required fields are filled"""
        return all([
            self.drinkType is not None,
            self.size is not None,
            self.milk is not None,
            self.name is not None
        ])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a warm, polite barista at Sukdeb Coffee Shop, a premium café known for its thoughtful and attentive service.
            The customer is speaking with you by voice, so your responses should sound natural, relaxed, and easy to follow.

            Your task is to help the customer place their coffee order by gathering a few key details:

            1. The type of drink they'd like (for example: latte, cappuccino, espresso, americano, mocha, cold brew, etc.)

            2. The size (small, medium, or large)

            3. Their preferred milk option (whole, 2%, oat, almond, soy, or no milk)

            4. Any additional extras they might want (such as whipped cream, an extra shot, vanilla syrup, caramel syrup, etc.) — optional

            5. The customer's name for the order

            Ask for this information one step at a time in a kind and patient manner.
            If the customer isn't sure what they want, feel free to offer a few helpful suggestions.

            After collecting all the details, read the full order back to the customer to make sure everything is correct before completing it.

            Keep your tone courteous, warm, and welcoming, and avoid complex formatting or special characters."""
        )
        self.order = OrderState()

    @function_tool
    async def save_order(self, context: RunContext):
        """Save the completed coffee order to a JSON file.
        
        Use this tool ONLY when you have confirmed all the order details with the customer
        and they have approved the final order.
        """
        
        if not self.order.is_complete():
            missing = []
            if not self.order.drinkType:
                missing.append("drink type")
            if not self.order.size:
                missing.append("size")
            if not self.order.milk:
                missing.append("milk preference")
            if not self.order.name:
                missing.append("customer name")
            
            return f"Cannot save order. Missing: {', '.join(missing)}"
        
        # Create orders directory if it doesn't exist
        orders_dir = "orders"
        os.makedirs(orders_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{orders_dir}/order_{timestamp}_{self.order.name.replace(' ', '_')}.json"
        
        # Save order to JSON file
        order_data = self.order.to_dict()
        order_data["timestamp"] = timestamp
        order_data["status"] = "confirmed"
        
        with open(filename, "w") as f:
            json.dump(order_data, f, indent=2)
        
        logger.info(f"Order saved to {filename}: {order_data}")
        
        return f"Perfect! Your order has been saved. Your {self.order.size} {self.order.drinkType} will be ready soon, {self.order.name}!"

    @function_tool
    async def update_order(
        self,
        context: RunContext,
        drinkType: Optional[str] = None,
        size: Optional[str] = None,
        milk: Optional[str] = None,
        extras: Optional[str] = None,
        name: Optional[str] = None
    ):
        """Update the current order with customer information.
        
        Use this tool to record each piece of information as the customer provides it.
        
        Args:
            drinkType: Type of coffee drink (e.g., latte, cappuccino, espresso)
            size: Size of drink (small, medium, large)
            milk: Milk preference (whole, 2%, oat, almond, soy, none)
            extras: Any extras like whipped cream, extra shot, syrups (can be comma-separated)
            name: Customer's name for the order
        """
        
        if drinkType:
            self.order.drinkType = drinkType
        if size:
            self.order.size = size.lower()
        if milk:
            self.order.milk = milk
        if extras:
            # Split comma-separated extras and add to list
            new_extras = [e.strip() for e in extras.split(",")]
            self.order.extras.extend(new_extras)
        if name:
            self.order.name = name
        
        # Build a summary of what we have so far
        summary = []
        if self.order.drinkType:
            summary.append(f"Drink: {self.order.drinkType}")
        if self.order.size:
            summary.append(f"Size: {self.order.size}")
        if self.order.milk:
            summary.append(f"Milk: {self.order.milk}")
        if self.order.extras:
            summary.append(f"Extras: {', '.join(self.order.extras)}")
        if self.order.name:
            summary.append(f"Name: {self.order.name}")
        
        current_status = " | ".join(summary) if summary else "No order details yet"
        
        logger.info(f"Order updated: {current_status}")
        
        return f"Got it! Current order: {current_status}"


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