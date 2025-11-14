import time
import random
import warnings
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.logger import get_logger
from utils.formatter import clean_text, format_email
from config import get_gemini_api_key
from utils.rate_limit_guard import rate_limit_safe_call  # new import

# Suppress non-critical warnings (like FutureWarning, DeprecationWarning)
warnings.filterwarnings("ignore")

logger = get_logger(__name__)

# --------------------------------------------------
# Gemini Response Helper (with Rate-Limit Guard)
# --------------------------------------------------
def _use_gemini(prompt: str, retry_attempts: int = 3) -> str:
    """
    Uses Gemini with retries, key rotation, and built-in rate-limit control.
    If rate-limit errors occur, waits automatically using rate_limit_safe_call().
    """
    for attempt in range(1, retry_attempts + 1):
        api_key = get_gemini_api_key()
        logger.info(f"[ResponseAgent] Attempt {attempt}/{retry_attempts} using Gemini key: {api_key[:6]}...")

        try:
            model = ChatGoogleGenerativeAI(
                model="gemini-2.5-pro",
                temperature=0.6,
                google_api_key=api_key,
            )

            # Run Gemini safely under rate-limit control
            response_obj = rate_limit_safe_call(model.invoke, prompt)
            response_text = clean_text(response_obj.content).strip()

            if not response_text:
                logger.warning("[ResponseAgent] Empty response from Gemini, retrying...")
                raise ValueError("Empty response")

            return response_text

        except Exception as e:
            error_message = str(e).lower()

            if "quota" in error_message or "429" in error_message:
                logger.warning(f"[ResponseAgent] Gemini quota exceeded for key {api_key[:6]} — rotating and retrying.")
                continue

            if "timeout" in error_message or "network" in error_message:
                logger.warning("[ResponseAgent] Temporary network issue, retrying in 5s...")
                time.sleep(5)
                continue

            logger.error(f"[ResponseAgent] Gemini API error: {e}")
            raise e

    raise RuntimeError("Gemini response generation failed after all retries.")


# --------------------------------------------------
# Main Response Generator
# --------------------------------------------------
def generate_response(email: dict, summary: str, recipient_name: str, your_name: str) -> str:
    """
    Generates a professional email response using Gemini with fallback.
    Automatically handles rate limits and network errors.
    """
    subject = email.get("subject", "").strip()
    content = email.get("body", "").strip() or "(No content provided)"

    prompt_template = PromptTemplate(
        input_variables=["recipient_name", "subject", "content", "summary", "your_name"],
        template=(
            "You are a professional AI email assistant named {your_name} at ShipCube Logistics.\n"
            "Write only the main body text of a formal email reply for {recipient_name}.\n"
            "Do not include greeting or closing lines.\n"
            "Keep the tone polite, concise, and business-appropriate.\n\n"
            "Original Email Details:\n"
            "From: {recipient_name}\n"
            "Subject: {subject}\n"
            "Content: {content}\n\n"
            "Summary of Intent:\n{summary}\n\n"
            "Now write the email body only:\n"
        ),
    )

    prompt = prompt_template.format(
        recipient_name=recipient_name,
        subject=subject,
        content=content,
        summary=summary,
        your_name=your_name,
    )

    try:
        response_text = _use_gemini(prompt)
        logger.debug(f"[ResponseAgent] Raw Gemini output: {response_text}")

    except Exception as e:
        logger.error(f"[ResponseAgent] Gemini failed: {e}")
        response_text = (
            "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
        )

    # Double safety check — never allow an empty body
    if not response_text.strip():
        logger.warning("[ResponseAgent] Empty AI output — using fallback message.")
        response_text = (
            "Thank you for reaching out. We’ve received your message and our team will get back to you shortly."
        )

    formatted_response = format_email(
        subject=subject,
        recipient_name=recipient_name,
        body=response_text,
        user_name=your_name,
    )

    logger.info(f"[ResponseAgent] Response generated successfully for subject: '{subject}'")
    return formatted_response.strip()
