# import logging
# import random
# import json
# from typing import Annotated

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


# class GameState:
#     """Tracks the D&D game world state"""

#     def __init__(self):
#         self.game_started = False
#         self.player = {
#             "name": "Adventurer",
#             "class": "Wanderer",
#             "hp": 20,
#             "max_hp": 20,
#             "inventory": ["rusty sword", "leather pouch with 10 gold coins"],
#             "traits": ["curious", "brave"],
#         }
#         self.location = {
#             "name": "The Crossroads Tavern",
#             "description": "A warm, bustling tavern at the edge of civilization",
#             "paths": [
#                 "north to the Dark Forest",
#                 "east to the Mountain Pass",
#                 "south to the Coastal Village",
#             ],
#         }
#         self.events = []
#         self.quests = []

#     def to_dict(self):
#         return {
#             "game_started": self.game_started,
#             "player": self.player,
#             "location": self.location,
#             "events": self.events,
#             "quests": self.quests,
#         }

#     def set_player_name(self, name: str):
#         self.player["name"] = name

#     def start_game(self):
#         self.game_started = True

#     def add_event(self, event: str):
#         self.events.append(event)

#     def add_item(self, item: str):
#         self.player["inventory"].append(item)

#     def remove_item(self, item: str):
#         if item in self.player["inventory"]:
#             self.player["inventory"].remove(item)
#             return True
#         return False

#     def update_hp(self, change: int):
#         self.player["hp"] = max(
#             0, min(self.player["max_hp"], self.player["hp"] + change)
#         )


# class Assistant(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions="""
# You are a Game Master for 'The Dragon's Quest' - a fantasy adventure with dragons, magic, and mysteries.

# GREETING PHASE (when game hasn't started):
# - Warmly greet the player
# - Introduce yourself as the Game Master
# - Ask for the player's name
# - Welcome them to 'The Dragon's Quest'
# - Ask if they're ready to begin the adventure
# - Wait for their confirmation before starting the story

# WORLD SETTING:
# - Medieval fantasy world with dragons, magic, elves, and dwarves
# - Dark forests, tall mountains, old ruins, and magical creatures
# - Magic exists but is rare and dangerous
# - The world has both wonder and danger

# YOUR JOB AS GAME MASTER:
# - Describe scenes in a clear and exciting way
# - Tell the player what happens after their actions
# - Control all characters, monsters, and the world
# - Remember everything that happens in the story
# - Make the story exciting and fun

# HOW TO TELL THE STORY:
# - Use simple, clear language that's easy to understand
# - Keep your responses short
# - Describe what the player sees, hears, and smells
# - Add some humor when it fits
# - NO emojis, asterisks, or special symbols

# GAME RULES:
# 1. Describe what's happening now
# 2. Give the player a choice or challenge
# 3. ALWAYS ask "What do you do?" or something similar at the end
# 4. Continue the story based on what the player says

# IMPORTANT:
# - Remember character names, places, and past choices
# - Keep track of items, health, and story events
# - Use dice rolls when the player tries risky actions
# - Keep the story moving with clear choices
# - Create interesting characters and places
# - Build up to exciting moments

# EXTRA INSTRUCTION:
# Whenever you ask "What do you do?" or a similar prompt, always suggest 2-4 possible actions the player can take, based on the current scene. For example: "You can talk to the bartender, look around the tavern, check your inventory, or try to leave." Make sure these options are relevant to the story and location, but also allow the player to choose something else if they wish.

# Use simple words and short sentences. Make it easy to understand but still exciting!

# Once the game starts, the adventure begins at a tavern. Guide the player into a fun quest!
# """,
#         )
#         self.game_state = GameState()

#     @function_tool
#     async def set_player_name_and_start(
#         self,
#         context: RunContext,
#         player_name: Annotated[str, "The name the player chose for their character"],
#     ) -> str:
#         """Set the player's name and start the game.

#         Use this when the player tells you their name during the greeting phase.
#         After calling this, you can begin the adventure.
#         """
#         self.game_state.set_player_name(player_name)
#         self.game_state.start_game()
#         return f"Player name set to {player_name}. Game is now starting!"

#     @function_tool
#     async def get_character_status(self, context: RunContext) -> str:
#         """Get the current character status including HP, inventory, and traits.

#         Use this when the player asks about their character, inventory, or health.
#         """
#         state = self.game_state.player
#         inventory_list = (
#             ", ".join(state["inventory"]) if state["inventory"] else "nothing"
#         )

#         return f"""Character: {state["name"]} the {state["class"]}
# Health: {state["hp"]}/{state["max_hp"]} HP
# Inventory: {inventory_list}
# Traits: {", ".join(state["traits"])}"""

#     @function_tool
#     async def roll_dice(
#         self,
#         context: RunContext,
#         dice_type: Annotated[int, "Type of dice to roll (6, 10, 20)"] = 20,
#         modifier: Annotated[int, "Modifier to add to the roll"] = 0,
#         difficulty: Annotated[int, "Difficulty class for the check"] = 10,
#     ) -> str:
#         """Roll dice for skill checks, attacks, or other random events.

#         Args:
#             dice_type: The type of dice (6, 10, or 20)
#             modifier: Bonus or penalty to add
#             difficulty: The target number to beat
#         """
#         roll = random.randint(1, dice_type)
#         total = roll + modifier
#         success = total >= difficulty

#         result = f"Rolling d{dice_type}... You rolled {roll}"
#         if modifier != 0:
#             result += f" + {modifier} = {total}"
#         result += f" (DC {difficulty}): {'SUCCESS!' if success else 'FAILURE'}"

#         logger.info(f"Dice roll: {result}")
#         return result

#     @function_tool
#     async def update_inventory(
#         self,
#         context: RunContext,
#         action: Annotated[str, "Either 'add' or 'remove'"],
#         item: Annotated[str, "The item to add or remove"],
#     ) -> str:
#         """Update the player's inventory by adding or removing items.

#         Args:
#             action: Either 'add' or 'remove'
#             item: The item name
#         """
#         if action == "add":
#             self.game_state.add_item(item)
#             return f"Added {item} to inventory"
#         elif action == "remove":
#             if self.game_state.remove_item(item):
#                 return f"Removed {item} from inventory"
#             else:
#                 return f"{item} not found in inventory"
#         return "Invalid action"


# def prewarm(proc: JobProcess):
#     proc.userdata["vad"] = silero.VAD.load()


# async def entrypoint(ctx: JobContext):
#     # Logging setup
#     # Add any other context you want in all log entries here
#     ctx.log_context_fields = {
#         "room": ctx.room.name,
#     }

#     # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector
#     session = AgentSession(
#         # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
#         # See all available models at https://docs.livekit.io/agents/models/stt/
#         stt=deepgram.STT(model="nova-3"),
#         # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
#         # See all available models at https://docs.livekit.io/agents/models/llm/
#         llm=google.LLM(
#             model="gemini-2.5-flash",
#         ),
#         # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
#         # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
#         tts=murf.TTS(
#             voice="en-US-matthew",
#             style="Conversation",
#             tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
#             text_pacing=True,
#         ),
#         # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
#         # See more at https://docs.livekit.io/agents/build/turns
#         turn_detection=MultilingualModel(),
#         vad=ctx.proc.userdata["vad"],
#         # allow the LLM to generate a response while waiting for the end of turn
#         # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
#         preemptive_generation=True,
#     )

#     # To use a realtime model instead of a voice pipeline, use the following session setup instead.
#     # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))
#     # 1. Install livekit-agents[openai]
#     # 2. Set OPENAI_API_KEY in .env.local
#     # 3. Add `from livekit.plugins import openai` to the top of this file
#     # 4. Use the following session setup instead of the version above
#     # session = AgentSession(
#     #     llm=openai.realtime.RealtimeModel(voice="marin")
#     # )

#     # Metrics collection, to measure pipeline performance
#     # For more information, see https://docs.livekit.io/agents/build/metrics/
#     usage_collector = metrics.UsageCollector()

#     @session.on("metrics_collected")
#     def _on_metrics_collected(ev: MetricsCollectedEvent):
#         metrics.log_metrics(ev.metrics)
#         usage_collector.collect(ev.metrics)

#     async def log_usage():
#         summary = usage_collector.get_summary()
#         logger.info(f"Usage: {summary}")

#     ctx.add_shutdown_callback(log_usage)

#     # # Add a virtual avatar to the session, if desired
#     # # For other providers, see https://docs.livekit.io/agents/models/avatar/
#     # avatar = hedra.AvatarSession(
#     #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra
#     # )
#     # # Start the avatar and wait for it to join
#     # await avatar.start(session, room=ctx.room)

#     # Start the session, which initializes the voice pipeline and warms up the models
#     await session.start(
#         agent=Assistant(),
#         room=ctx.room,
#         room_input_options=RoomInputOptions(
#             # For telephony applications, use `BVCTelephony` for best results
#             noise_cancellation=noise_cancellation.BVC(),
#         ),
#     )

#     # Join the room and connect to the user
#     await ctx.connect()


# if __name__ == "__main__":
#     cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))


import logging
import random
import json
from typing import Annotated

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


class GameState:
    """Tracks the fantasy game world state"""

    def __init__(self):
        self.game_started = False
        self.player = {
            "name": "Initiate",
            "class": "Lightbound Initiate",
            "hp": 22,
            "max_hp": 22,
            "inventory": [
                "glimmer dagger",
                "moonstone amulet",
                "satchel with 12 silver shards",
            ],
            "traits": ["resilient", "perceptive"],
        }
        self.location = {
            "name": "Moonspire Haven",
            "description": "A quiet mountain village beneath the glowing Moonspire Tower, where the light is starting to flicker.",
            "paths": [
                "west to the Whispering Woods",
                "north to the Frostwind Ridge",
                "south to the Emberfall Ruins",
            ],
        }
        self.events = []
        self.quests = []

    def to_dict(self):
        return {
            "game_started": self.game_started,
            "player": self.player,
            "location": self.location,
            "events": self.events,
            "quests": self.quests,
        }

    def set_player_name(self, name: str):
        self.player["name"] = name

    def start_game(self):
        self.game_started = True

    def add_event(self, event: str):
        self.events.append(event)

    def add_item(self, item: str):
        self.player["inventory"].append(item)

    def remove_item(self, item: str):
        if item in self.player["inventory"]:
            self.player["inventory"].remove(item)
            return True
        return False

    def update_hp(self, change: int):
        self.player["hp"] = max(
            0, min(self.player["max_hp"], self.player["hp"] + change)
        )


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
You are a Game Master for 'Shadowfall Chronicles' – a fantasy adventure set in the world of Elarion, where a creeping darkness called the Shadowfall slowly eats away at the light.

GREETING PHASE (when game hasn't started):
- Warmly greet the player.
- Introduce yourself as the Game Master.
- Ask for the player's name.
- Welcome them to 'Shadowfall Chronicles'.
- Briefly hint that the Moonspire Tower's light is fading.
- Ask if they're ready to begin the adventure.
- Wait for their confirmation before starting the story.

WORLD SETTING:
- The world is called Elarion, filled with magic, ancient ruins, and dangerous shadows.
- The main region is around the mountain village 'Moonspire Haven'.
- At the center stands the Moonspire Tower, a tall crystal tower that keeps the Shadowfall at bay.
- The tower's light is flickering; if the light dies, the Shadowfall will consume Elarion.
- Nearby locations:
  - Whispering Woods: a forest where the trees seem to whisper warnings.
  - Frostwind Ridge: icy cliffs guarded by ancient, half-forgotten spirits.
  - Emberfall Ruins: the broken remains of an old city, now haunted by shadow creatures.

PLAYER CHARACTER:
- The player is a 'Lightbound Initiate' – a trainee warrior-mage bound to the light of Moonspire.
- They are just starting their journey against the Shadowfall.
- They carry a glimmer dagger, a moonstone amulet, and a small satchel of silver shards.

YOUR JOB AS GAME MASTER:
- Describe scenes in a clear and exciting way.
- Tell the player what happens after their actions.
- Control all characters, creatures, and the world.
- Remember everything that happens in the story.
- Make the story exciting and fun, but still easy to understand.

HOW TO TELL THE STORY:
- Use simple, clear language that's easy to understand.
- Keep your responses short.
- Describe what the player sees, hears, and feels.
- Add a little humor when it fits.
- NO emojis, asterisks, or special symbols.

MAIN QUEST HOOK:
- The Moonspire Tower's light is weakening.
- If the light goes out, the Shadowfall will cover the land.
- The player must discover why the light is fading and how to restore it.
- Important NPCs you can introduce:
  - Eira Solwind: the calm but worried guardian of the Moonspire Tower.
  - Korin Blackroot: a tracker from the Whispering Woods who has seen strange shadows.
  - Eldric the Frostbound: an old wanderer who knows secrets about Frostwind Ridge.

GAME RULES:
1. Always describe what is happening right now.
2. Give the player a choice or challenge.
3. ALWAYS end with a question like "What do you do?" or something similar.
4. Always suggest 2–4 possible actions the player can take.
5. Then let the player choose any option, even something different.

DICE AND RISK:
- Use dice rolls when the player tries risky actions (climbing, sneaking, fighting, persuading, etc.).
- On success, describe a positive but believable outcome.
- On failure, describe a setback, wound, loss of item, or new danger, but keep the story moving.

INVENTORY AND STATUS:
- Respect the player's inventory and traits.
- If they get a new item, you can ask the 'update_inventory' tool to add it.
- If they lose or use something, you can remove it.
- For damage or healing, imagine using 'update_hp' (even if you do it in world description).

EXTRA INSTRUCTION:
Whenever you ask "What do you do?" or a similar prompt, always suggest 2–4 possible actions the player can take, based on the current scene.
For example:
"You can talk to Eira near the tower steps, explore the village square, check your inventory, or head toward the Whispering Woods."
Make sure these options are relevant to the story and location, but always allow the player to choose something else if they wish.

STARTING SCENE:
- Once the game starts, the adventure begins in Moonspire Haven, at the base of the Moonspire Tower.
- The night sky is dim, the tower's light is flickering, and people look worried.
- Gently guide the player into a first small mission: talking to someone important, noticing a strange sign, or choosing a direction to investigate.

Use simple words and short sentences. Make it easy to understand but still exciting!
""",
        )
        self.game_state = GameState()

    @function_tool
    async def set_player_name_and_start(
        self,
        context: RunContext,
        player_name: Annotated[str, "The name the player chose for their character"],
    ) -> str:
        """Set the player's name and start the game.

        Use this when the player tells you their name during the greeting phase.
        After calling this, you can begin the adventure.
        """
        self.game_state.set_player_name(player_name)
        self.game_state.start_game()
        return f"Player name set to {player_name}. The light of Moonspire calls you. The game is now starting!"

    @function_tool
    async def get_character_status(self, context: RunContext) -> str:
        """Get the current character status including HP, inventory, and traits.

        Use this when the player asks about their character, inventory, or health.
        """
        state = self.game_state.player
        inventory_list = (
            ", ".join(state["inventory"]) if state["inventory"] else "nothing"
        )

        return (
            f"Character: {state['name']} the {state['class']}\n"
            f"Health: {state['hp']}/{state['max_hp']} HP\n"
            f"Inventory: {inventory_list}\n"
            f"Traits: {', '.join(state['traits'])}"
        )

    @function_tool
    async def roll_dice(
        self,
        context: RunContext,
        dice_type: Annotated[int, "Type of dice to roll (6, 10, 20)"] = 20,
        modifier: Annotated[int, "Modifier to add to the roll"] = 0,
        difficulty: Annotated[int, "Difficulty class for the check"] = 10,
    ) -> str:
        """Roll dice for skill checks, attacks, or other random events.

        Args:
            dice_type: The type of dice (6, 10, or 20)
            modifier: Bonus or penalty to add
            difficulty: The target number to beat
        """
        roll = random.randint(1, dice_type)
        total = roll + modifier
        success = total >= difficulty

        result = f"Rolling d{dice_type}... You rolled {roll}"
        if modifier != 0:
            result += f" + {modifier} = {total}"
        result += f" (DC {difficulty}): {'SUCCESS!' if success else 'FAILURE'}"

        logger.info(f"Dice roll: {result}")
        return result

    @function_tool
    async def update_inventory(
        self,
        context: RunContext,
        action: Annotated[str, "Either 'add' or 'remove'"],
        item: Annotated[str, "The item to add or remove"],
    ) -> str:
        """Update the player's inventory by adding or removing items.

        Args:
            action: Either 'add' or 'remove'
            item: The item name
        """
        if action == "add":
            self.game_state.add_item(item)
            return f"Added {item} to inventory."
        elif action == "remove":
            if self.game_state.remove_item(item):
                return f"Removed {item} from inventory."
            else:
                return f"{item} not found in inventory."
        return "Invalid action. Use 'add' or 'remove'."


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
