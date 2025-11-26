"""SDR Voice Agent for GO Classes - GATE / UGC NET lead generation."""

import json
import logging
import os
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
    RunContext,
    ToolError,
    WorkerOptions,
    cli,
    function_tool,
    metrics,
)
from livekit.plugins import silero, murf, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Load FAQ / company data
FAQ_FILE = Path(__file__).parent / "company_faq.json"
with open(FAQ_FILE, "r", encoding="utf-8") as f:
    COMPANY_DATA = json.load(f)


class Assistant(Agent):
    def __init__(self) -> None:
        # Lead info for this call/session
        self.lead_data = {
            "name": None,              # Student or working professional name
            "current_status": None,    # e.g. B.Tech 3rd year, M.Sc, Working Professional
            "target_exam": None,       # e.g. GATE CSE, GATE DA, UGC NET CS
            "target_year": None,       # e.g. 2026 / 2027 / 2028
            "contact": None,           # phone or email
            "background": None,        # college/branch or work background
            "current_preparation": None,  # e.g. self-study, other coaching, just starting
            "weak_areas": None,        # subjects/topics they struggle with
            "timeline": None,          # when they plan to join
        }

        company_name = COMPANY_DATA["company"]["name"]

        super().__init__(
            instructions=f"""
        You are Sachin Mittal, a warm and professional **Sales Development Representative (SDR)** for {company_name}.

        Company Overview:
        {COMPANY_DATA['company']['description']}

        Your job in every conversation:
        - Greet the visitor warmly and introduce yourself as "Sachin Mittal from GO Classes".
        - Ask for their **name very early** and WAIT for their reply before going deep into details.
        - Ask what exam they are targeting: **GATE CSE, GATE DA, or UGC NET (Computer Science)**.
        - Ask which **year** they are targeting (2026 / 2027 / 2028, etc.).
        - Understand their **current status** (B.Tech year, M.Sc, working professional, dropout, etc.).
        - Understand their **current preparation** (self-study, other coaching, test series only, just starting).
        - Ask gently about any **weak subjects or topics** (OS, CN, TOC, Maths, etc.).
        - Ask for the **best contact** (phone or email) in a natural way.
        - Keep the conversation friendly, focused on their needs and doubts.
        - Answer questions about what GO Classes does, courses, pricing basics, free resources, and who it is for.

        Very important - during the call you MUST collect, in a natural way:
        1. Name
        2. Current status (student year / working / etc.)
        3. Target exam (GATE CSE, GATE DA, UGC NET CS)
        4. Target year
        5. Contact (phone or email - "best way to reach you")
        6. Background (college/branch or work profile)
        7. Current preparation approach
        8. Weak areas / subjects
        9. Timeline to join (now / soon / later / just exploring)

        Tools you can use:
        - `search_faq` → when user asks anything about GO Classes, courses, features, pricing, free content, test series, etc.
        - `save_lead_name`, `save_current_status`, `save_target_exam`, `save_target_year`,
        `save_contact`, `save_background`, `save_current_preparation`, `save_weak_areas`,
        `save_timeline` → whenever the user gives you that information in conversation.
        - `end_call_summary` → when the user says things like "that's all", "I'm done", "thank you" or clearly wants to end.

        Response style:
        - You are speaking over **voice**.
        - Be short, clear and conversational. No bullets, no lists, no markdown, no emojis.
        - Never invent pricing or features beyond what the FAQ tool returns from `company_faq.json`.
        - If something is not in the FAQ, speak honestly and say they can check the GO Classes website or contact support.

        At the end of the call:
        - Call `end_call_summary` to save all collected info into a JSON file.
        - Give a short spoken summary: who they are, what they want, their target exam/year, and approximate timeline.
        """
                )

    # ========= FAQ SEARCH TOOL =========
    @function_tool
    async def search_faq(self, context: RunContext, question: str):
        """Search the company FAQ to answer questions about GO Classes products, services, pricing, or company information.

        Use this when the user asks about:
        - What GO Classes does
        - GATE / UGC NET preparation
        - Course features and structure
        - Pricing or discounts
        - Free courses or YouTube content
        - Test series and quizzes
        - Who these courses are for
        """
        logger.info(f"Searching FAQ for: {question!r}")

        question_lower = question.lower()

        # If clearly about prices
        if any(
            word in question_lower
            for word in ["price", "cost", "fee", "fees", "charge", "discount", "free", "paid", "subscription"]
        ):
            pricing = COMPANY_DATA["pricing"]
            return (
                f"For pricing basics: "
                f"GATE CSE Complete Course is around {pricing['gate_cse_complete']}. "
                f"GATE DA Complete Course is around {pricing['gate_da_complete']}. "
                f"The GATE CSE + DA Combo is around {pricing['gate_combo']}. "
                f"Test series and quizzes are {pricing['test_series']}. "
                f"We also offer {pricing['free_courses']} "
                f"(exact prices may change, so we always recommend checking the GO Classes website for latest offers)."
            )

        # Simple keyword-overlap matching over FAQ
        best_match = None
        best_score = 0

        q_words = set(question_lower.split())
        for faq in COMPANY_DATA["faq"]:
            text = (faq["question"] + " " + faq["answer"]).lower()
            faq_words = set(text.split())
            overlap = len(q_words.intersection(faq_words))
            if overlap > best_score:
                best_score = overlap
                best_match = faq

        if best_match and best_score > 0:
            return best_match["answer"]

        # Fallback: general company description
        return COMPANY_DATA["company"]["description"]

    # ========= LEAD CAPTURE TOOLS =========

    @function_tool
    async def save_lead_name(self, context: RunContext, name: str):
        """Save the lead's name when they mention it."""
        logger.info(f"Saving lead name: {name}")
        self.lead_data["name"] = name.strip()
        return f"Thanks, {name}. Nice to meet you!"

    @function_tool
    async def save_current_status(self, context: RunContext, current_status: str):
        """Save the lead's current status (student year / working / etc.)."""
        logger.info(f"Saving current status: {current_status}")
        self.lead_data["current_status"] = current_status.strip()
        return "Got it, I have noted your current status."

    @function_tool
    async def save_target_exam(self, context: RunContext, target_exam: str):
        """Save the exam they are targeting: GATE CSE, GATE DA, or UGC NET CS."""
        logger.info(f"Saving target exam: {target_exam}")
        self.lead_data["target_exam"] = target_exam.strip()
        return f"Great, so you are targeting {target_exam}."

    @function_tool
    async def save_target_year(self, context: RunContext, target_year: str):
        """Save the target exam year (e.g., 2026, 2027)."""
        logger.info(f"Saving target year: {target_year}")
        self.lead_data["target_year"] = target_year.strip()
        return f"Okay, targeting {target_year}."

    @function_tool
    async def save_contact(self, context: RunContext, contact: str):
        """Save the lead's preferred contact (phone or email)."""
        logger.info(f"Saving contact: {contact}")
        self.lead_data["contact"] = contact.strip()
        return "Perfect, I have saved your contact details."

    @function_tool
    async def save_background(self, context: RunContext, background: str):
        """Save college/branch or professional background."""
        logger.info(f"Saving background: {background}")
        self.lead_data["background"] = background.strip()
        return "Thanks, that background info really helps."

    @function_tool
    async def save_current_preparation(self, context: RunContext, current_preparation: str):
        """Save how they are currently preparing (self-study, other coaching, etc.)."""
        logger.info(f"Saving current preparation: {current_preparation}")
        self.lead_data["current_preparation"] = current_preparation.strip()
        return "Got it, I have noted your current preparation approach."

    @function_tool
    async def save_weak_areas(self, context: RunContext, weak_areas: str):
        """Save subjects/topics where they need help."""
        logger.info(f"Saving weak areas: {weak_areas}")
        self.lead_data["weak_areas"] = weak_areas.strip()
        return "No worries, we focus a lot on building strong concepts in those areas."

    @function_tool
    async def save_timeline(self, context: RunContext, timeline: str):
        """Save when they plan to enroll (now / soon / later / just exploring)."""
        logger.info(f"Saving timeline: {timeline}")
        self.lead_data["timeline"] = timeline.strip()
        return "Great, I have noted your timeline to get started."

    # ========= END-OF-CALL SUMMARY TOOL =========

    @function_tool
    async def end_call_summary(self, context: RunContext):
        """
        Generate and save the final lead summary when the call is ending.

        Use this when the user says things like:
        - "That's all", "I'm done", "Nothing else", "Thank you"
        - Or they clearly want to end the conversation.

        This will save a JSON file with all collected lead information.
        """
        logger.info("Generating end-of-call summary for lead")

        # Directory for logs
        output_dir = Path(__file__).parent / "logs"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"lead_{timestamp}.json"

        summary_data = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "company": COMPANY_DATA["company"]["name"],
            "lead_info": self.lead_data.copy(),
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Lead data saved to {output_file}")

        # Build a short spoken summary
        parts = []
        if self.lead_data["name"]:
            parts.append(f"We spoke with {self.lead_data['name']}")
        if self.lead_data["current_status"]:
            parts.append(f"who is currently {self.lead_data['current_status']}")
        if self.lead_data["target_exam"]:
            parts.append(f"and targeting {self.lead_data['target_exam']}")
        if self.lead_data["target_year"]:
            parts.append(f"for the {self.lead_data['target_year']} attempt")
        if self.lead_data["weak_areas"]:
            parts.append(f"with weaker areas in {self.lead_data['weak_areas']}")
        if self.lead_data["timeline"]:
            parts.append(f"and plans to join {self.lead_data['timeline']}")

        if parts:
            verbal_summary = ". ".join(parts)
        else:
            verbal_summary = "We had a detailed discussion about your preparation for competitive exams."

        return (
            f"Thank you so much for your time today. {verbal_summary}. "
            "I have saved your details, and the GO Classes team will reach out to you with the best plan for your preparation. "
            "All the best for your exam journey!"
        )


# ========= PREWARM FUNCTION =========


def prewarm(proc: JobProcess):
    """Prewarm models and load VAD / FAQ data."""
    proc.userdata["vad"] = silero.VAD.load()
    logger.info(f"Preloaded VAD and FAQ data for {COMPANY_DATA['company']['name']}")


# ========= ENTRYPOINT =========


async def entrypoint(ctx: JobContext):
    """Entry point for the GO Classes SDR agent."""

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-matthew",  # you can change to any Murf Falcon voice ID you like
            style="Conversation",
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

    @session.on("user_speech_committed")
    def _on_user_speech(ev):
        logger.info(f"✅ User speech: {ev.text}")

    @session.on("agent_speech_committed")
    def _on_agent_speech(ev):
        logger.info(f"✅ Agent speech: {ev.text}")

    @session.on("error")
    def _on_error(ev: ToolError):
        logger.error(f"❌ Session error: {ev}")

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage summary: {summary}")

    ctx.add_shutdown_callback(log_usage)

    agent = Assistant()

    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()
    logger.info("GO Classes SDR agent is live and listening.")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
