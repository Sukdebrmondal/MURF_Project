import logging
import json
from datetime import datetime
from pathlib import Path

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


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a friendly and helpful food & grocery ordering assistant for QuickMart Express.
            You help customers order groceries, snacks, and prepared food items through natural conversation.
            
            Your capabilities:
            - Add items to cart with quantities
            - Remove items from cart
            - Update quantities of items already in cart
            - Show what's currently in the cart
            - Intelligently add ingredients for recipes (e.g., "ingredients for pasta")
            - Place orders when the customer is ready
            
            Guidelines:
            - Be conversational and friendly
            - Confirm actions clearly (e.g., "I've added 2 loaves of bread to your cart")
            - Ask for clarification when needed (quantity, size, brand preferences)
            - Suggest items when appropriate
            - Keep responses concise and natural for voice interaction
            - Don't use emojis, asterisks, or complex formatting
            - When placing an order, ask for the customer's name
            """,
        )

        # Load catalog and recipes
        self.data_dir = Path(__file__).parent / "data"
        self.catalog = self._load_catalog()
        self.recipes = self._load_recipes()

        # Initialize cart (item_id -> quantity)
        self.cart: dict[str, int] = {}

    def _load_catalog(self):
        """Load the product catalog from JSON."""
        catalog_path = self.data_dir / "catalog.json"
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Create a dict for easy lookup by ID
                catalog = {item["id"]: item for item in data["items"]}
                logger.info(f"Loaded {len(catalog)} catalog items from {catalog_path}")
                return catalog
        except Exception as e:
            logger.error(f"Failed to load catalog from {catalog_path}: {e}")
            return {}

    def _load_recipes(self):
        """Load recipe mappings from JSON."""
        recipes_path = self.data_dir / "recipes.json"
        try:
            with open(recipes_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                recipes = data["recipes"]
                logger.info(f"Loaded {len(recipes)} recipes from {recipes_path}")
                return recipes
        except Exception as e:
            logger.error(f"Failed to load recipes from {recipes_path}: {e}")
            return {}

    def _find_item_by_name(self, item_name: str):
        """Find an item in catalog by name (fuzzy matching)."""
        item_name_lower = item_name.strip().lower()

        # First try exact match
        for item_id, item in self.catalog.items():
            if item["name"].lower() == item_name_lower:
                return item_id, item

        # Then try partial match
        for item_id, item in self.catalog.items():
            if item_name_lower in item["name"].lower():
                return item_id, item

        return None, None

    @function_tool
    async def add_to_cart(self, context: RunContext, item_name: str, quantity: int = 1):
        """Add an item to the shopping cart.

        Use this tool when the customer wants to add a specific item to their cart.

        Args:
            item_name: The name of the item to add (e.g., "bread", "milk", "peanut butter")
            quantity: The number of items to add (default is 1)
        """
        logger.info(f"Adding to cart: {item_name} x {quantity}")

        if quantity <= 0:
            return "Quantity must be at least 1. Please specify a valid quantity."

        item_id, item = self._find_item_by_name(item_name)

        if not item:
            return (
                f"Sorry, I couldn't find '{item_name}' in our catalog. "
                "Could you try a different item or be more specific?"
            )

        # Add to cart or update quantity
        if item_id in self.cart:
            self.cart[item_id] += quantity
        else:
            self.cart[item_id] = quantity

        total_qty = self.cart[item_id]
        return f"Added {quantity} {item['name']} to your cart. You now have {total_qty} in total."

    @function_tool
    async def remove_from_cart(self, context: RunContext, item_name: str):
        """Remove an item completely from the shopping cart.

        Use this tool when the customer wants to remove an item from their cart.

        Args:
            item_name: The name of the item to remove
        """
        logger.info(f"Removing from cart: {item_name}")

        item_id, item = self._find_item_by_name(item_name)

        if not item:
            return f"I couldn't find '{item_name}' in the catalog."

        if item_id not in self.cart:
            return f"{item['name']} is not in your cart."

        del self.cart[item_id]
        return f"Removed {item['name']} from your cart."

    @function_tool
    async def update_quantity(self, context: RunContext, item_name: str, quantity: int):
        """Update the quantity of an item already in the cart.

        Use this tool when the customer wants to change the quantity of an item.

        Args:
            item_name: The name of the item to update
            quantity: The new quantity (must be greater than 0)
        """
        logger.info(f"Updating quantity: {item_name} to {quantity}")

        if quantity <= 0:
            return "Quantity must be greater than 0. Use remove_from_cart to remove items."

        item_id, item = self._find_item_by_name(item_name)

        if not item:
            return f"I couldn't find '{item_name}' in the catalog."

        if item_id not in self.cart:
            return f"{item['name']} is not in your cart. Use add_to_cart to add it first."

        self.cart[item_id] = quantity
        return f"Updated {item['name']} quantity to {quantity}."

    @function_tool
    async def view_cart(self, context: RunContext):
        """Show the current contents of the shopping cart with prices and total.

        Use this tool when the customer asks what's in their cart or wants to review their order.
        """
        logger.info("Viewing cart")

        if not self.cart:
            return "Your cart is empty."

        cart_items = []
        total = 0

        for item_id, quantity in self.cart.items():
            item = self.catalog.get(item_id)
            if not item:
                # Skip unknown items just in case
                continue
            item_total = item["price"] * quantity
            total += item_total
            cart_items.append(f"{item['name']} x {quantity} - ₹{item_total}")

        if not cart_items:
            return "Your cart is empty."

        cart_summary = "\n".join(cart_items)
        return f"Your cart:\n{cart_summary}\n\nTotal: ₹{total}"

    @function_tool
    async def add_ingredients_for(self, context: RunContext, recipe_name: str):
        """Add all ingredients needed for a specific recipe or meal.

        Use this tool when the customer asks for ingredients for a specific dish or meal.

        Args:
            recipe_name: The name of the recipe or meal (e.g., "pasta", "peanut butter sandwich", "salad")
        """
        logger.info(f"Adding ingredients for: {recipe_name}")

        recipe_name_lower = recipe_name.strip().lower()

        # Find matching recipe
        recipe = None
        for recipe_key, recipe_data in self.recipes.items():
            if (
                recipe_key.lower() == recipe_name_lower
                or recipe_name_lower in recipe_key.lower()
            ):
                recipe = recipe_data
                break

        if not recipe:
            return (
                f"Sorry, I don't have a recipe for '{recipe_name}'. "
                "I can help you add specific items instead."
            )

        # Add all items from the recipe
        added_items = []
        for item_id in recipe["items"]:
            if item_id in self.catalog:
                if item_id in self.cart:
                    self.cart[item_id] += 1
                else:
                    self.cart[item_id] = 1
                added_items.append(self.catalog[item_id]["name"])

        if not added_items:
            return (
                f"Sorry, I couldn't add items for '{recipe_name}' "
                "because they are missing from the catalog."
            )

        items_list = ", ".join(added_items)
        return f"I've added the ingredients for {recipe['description']}: {items_list}."

    @function_tool
    async def place_order(self, context: RunContext, customer_name: str):
        """Place the order and save it to a file.

        Use this tool when the customer is ready to finalize and place their order.

        Args:
            customer_name: The customer's name for the order
        """
        logger.info(f"Placing order for: {customer_name}")

        if not self.cart:
            return "Your cart is empty. Please add some items before placing an order."

        # Calculate order details
        order_items = []
        total = 0

        for item_id, quantity in self.cart.items():
            item = self.catalog.get(item_id)
            if not item:
                # Skip unknown items just in case
                continue
            item_total = item["price"] * quantity
            total += item_total
            order_items.append(
                {
                    "item_id": item_id,
                    "name": item["name"],
                    "quantity": quantity,
                    "price_per_unit": item["price"],
                    "total": item_total,
                }
            )

        if not order_items:
            return "There was a problem reading your cart items. Please try again."

        # Create order object
        timestamp = datetime.now()
        order_id = f"ORD{timestamp.strftime('%Y%m%d%H%M%S')}"

        order = {
            "order_id": order_id,
            "customer_name": customer_name,
            "timestamp": timestamp.isoformat(),
            "items": order_items,
            "total": total,
            "status": "received",
        }

        # Save order to file
        orders_dir = self.data_dir / "orders"
        orders_dir.mkdir(parents=True, exist_ok=True)

        order_file = orders_dir / f"{order_id}.json"

        try:
            with open(order_file, "w", encoding="utf-8") as f:
                json.dump(order, f, indent=2)

            # Clear the cart
            self.cart = {}

            return (
                f"Order placed successfully! Your order ID is {order_id}. "
                f"Total amount: ₹{total}. Thank you for shopping with QuickMart Express, {customer_name}!"
            )

        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return "Sorry, there was an error placing your order. Please try again."


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
