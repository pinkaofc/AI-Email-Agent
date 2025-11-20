import time
import random
import warnings
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from utils.logger import get_logger
from utils.formatter import clean_text
from config import get_gemini_api_key
from utils.rate_limit_guard import rate_limit_safe_call
from utils.custom_fallbacks import get_custom_fallback   # <-- NEW IMPORT

warnings.filterwarnings("ignore")
logger = get_logger(__name__)


# ============================================================
#                   GEMINI SAFE CALL WRAPPER
# ============================================================
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Uses Gemini with:
      - key rotation
      - rate limit protection
      - retry logic
      - clean output normalization
    Returns ONLY raw body text.
    """
    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()
        logger.info(f"[ResponseAgent] Attempt {attempt}/{retry_attempts} using key: {api_key[:6]}...")

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.4,
                google_api_key=api_key,
            )

            # Use the rate limit wrapper
            response_obj = rate_limit_safe_call(model.invoke, prompt)
            response_text = clean_text(response_obj.content).strip()

            if not response_text:
                logger.warning("[ResponseAgent] Gemini returned empty text — retrying...")
                raise ValueError("Empty response")

            return response_text

        except Exception as e:
            err = str(e).lower()

            if "429" in err or "quota" in err:
                logger.warning(f"[ResponseAgent] Quota exceeded on key {api_key[:6]} — rotating.")
                continue

            if "timeout" in err or "network" in err:
                logger.warning("[ResponseAgent] Network timeout — retry after 5s.")
                time.sleep(5)
                continue

            logger.error(f"[ResponseAgent] Gemini hard error: {e}")
            raise e

    raise RuntimeError("Gemini failed after all retries.")


# ============================================================
#          MAIN SAFE RESPONSE BODY GENERATOR
# ============================================================
def generate_response(email: dict, summary: str, recipient_name: str, your_name: str) -> str:
    """
    Produces ONLY raw body text for the reply.
    Supervisor wraps it with greeting + closing.

    STRICT RULES:
    - Never invent operational details
    - Never add internal workflow details
    - Never guess shipments, refunds, timelines, tracking
    """
    subject = email.get("subject", "").strip()
    content = email.get("body", "").strip() or "(No content provided)"

    # =============== PROMPT (ANTI-HALLUCINATION SAFE) ===============
    prompt_template = PromptTemplate(
        input_variables=["recipient_name", "subject", "content", "summary", "your_name"],
        template=(
            "You are an AI email assistant named {your_name} at ShipCube Logistics.\n\n"
            "Write ONLY the main body text (no greeting, no closing).\n\n"

            "================ SAFETY RULES ================\n"
            "DO NOT invent or guess:\n"
            "- tracking numbers\n"
            "- delivery dates\n"
            "- refund amounts\n"
            "- investigation results\n"
            "- SKU counts, carton counts\n"
            "- any operational detail not provided\n\n"
            "If information is missing → reply that the operations team will verify and follow up.\n"
            "================================================\n\n"

            "Customer Name: {recipient_name}\n"
            "Subject: {subject}\n"
            "Email Content: {content}\n\n"
            "Intent Summary:\n{summary}\n\n"
            "Now respond with ONLY the body text:\n"
        ),
    )

    prompt = prompt_template.format(
        recipient_name=recipient_name,
        subject=subject,
        content=content,
        summary=summary,
        your_name=your_name,
    )

    # ============================================================
    #              TRY GEMINI → IF FAIL → TEMPLATE FALLBACK
    # ============================================================
    try:
        llm_text = _use_gemini(prompt).strip()

        # If Gemini returns nonsense or empty → fallback
        if not llm_text or len(llm_text) < 5:
            logger.warning("[ResponseAgent] Gemini returned unusable output. Using custom fallback.")
            return get_custom_fallback(summary, email.get("classification", ""))

        logger.debug(f"[ResponseAgent] Safe Gemini output: {llm_text!r}")
        return llm_text

    except Exception as e:
        logger.error(f"[ResponseAgent] LLM failed → using custom fallback. Error: {e}")
        return get_custom_fallback(summary, email.get("classification", ""))

