import json
from agents.response_agent import generate_response
from agents.human_review_agent import review_email
from core.email_sender import send_email
from utils.logger import get_logger

logger = get_logger(__name__)

# --- Simple rule-based summarizer for testing ---
def dummy_summarize_email(email_body: str) -> str:
    body_lower = email_body.lower()
    if "damaged" in body_lower:
        return "Customer reported damaged goods and requested replacement or refund."
    elif "missing" in body_lower:
        return "Customer reported missing items in shipment and requested resend."
    elif "invoice" in body_lower:
        return "Customer requested an official invoice for an order."
    elif "delivered" in body_lower and "not received" in body_lower:
        return "Customer claims the shipment is marked delivered but was not received."
    elif "appreciation" in body_lower or "thank you" in body_lower:
        return "Customer expressed appreciation for quick issue resolution."
    elif "delivery estimate" in body_lower or "update" in body_lower:
        return "Customer requested delivery status update."
    elif "customs" in body_lower:
        return "Customer mentioned customs documentation issue."
    else:
        return "General customer inquiry regarding order or shipment."
# --------------------------------------------------------


def run_test_email_response_flow(email_data: dict):
    """
    Runs a full test flow for a single email using Gemini-based response generation.
    """

    # Derive recipient name from email address (e.g., james.liu@... -> James)
    sender_email = email_data.get("from", "")
    if "@" in sender_email:
        local_part = sender_email.split("@")[0]
        recipient_name = local_part.split(".")[0].capitalize()
    else:
        recipient_name = "Customer"

    your_company_name = "ShipCube"

    print("\n--- Processing Test Email ---")
    print(f"From: {email_data.get('from')}")
    print(f"Subject: {email_data.get('subject')}")
    print(f"Body:\n{email_data.get('body')}")
    print("----------------------------------------")

    # 1. Summarize
    summary = dummy_summarize_email(email_data.get("body", ""))
    logger.info(f"[Test] Summary: {summary}")

    # 2. Generate AI Response (Gemini)
    try:
        ai_response = generate_response(
            email=email_data,
            summary=summary,
            recipient_name=recipient_name,
            your_name=your_company_name
        )
        logger.info(f"[Test] AI-generated response:\n{ai_response}")
    except Exception as e:
        logger.error(f"[Test] Error generating response: {e}", exc_info=True)
        return

    # 3. Human review (manual approval/modification)
    final_response = review_email(email_data, ai_response)
    if final_response != ai_response:
        logger.info("[Test] Response modified by human reviewer.")
    else:
        logger.info("[Test] Human review approved AI response.")

    # 4. Prepare message structure for sending
    email_to_send = {
        "subject": email_data.get("subject", ""),
        "response": final_response,
        "from": email_data.get("from", "")
    }

    # 5. Attempt to send (SMTP)
    try:
        sent = send_email(email_to_send, your_company_name)
        if sent:
            print(f" Email ID {email_data.get('id')} sent successfully.")
            logger.info(f"[Test] Email ID {email_data.get('id')} sent successfully.")
        else:
            print(f" Failed to send email ID {email_data.get('id')}.")
            logger.warning(f"[Test] Failed to send email ID {email_data.get('id')}.")
    except Exception as e:
        logger.error(f"[Test] Error during send_email: {e}", exc_info=True)


if __name__ == "__main__":
    # Load your JSON email samples
    try:
        with open("sample_emails.json", "r", encoding="utf-8") as f:
            email_samples = json.load(f)
    except FileNotFoundError:
        print("Error: 'sample_emails.json' not found. Please add your test data file.")
        email_samples = []

    # Choose a test email ID (or loop through all)
    test_email_id = 8  # e.g., "Damaged Goods" or any other ID
    selected_email = next((e for e in email_samples if e["id"] == str(test_email_id)), None)

    if selected_email:
        run_test_email_response_flow(selected_email)
    else:
        print(f"Email with ID {test_email_id} not found in samples.")
