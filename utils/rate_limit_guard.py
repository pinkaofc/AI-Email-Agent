import time
import logging

logger = logging.getLogger("rate_limit_guard")

def rate_limit_safe_call(func, *args, max_retries=3, cooldown=35, **kwargs):
    """
    Executes an API call safely with built-in handling for Gemini 429 errors.
    
    Args:
        func: Callable API function (e.g., Gemini or LangChain call)
        *args, **kwargs: Arguments passed to the function
        max_retries: How many times to retry on 429 or network errors
        cooldown: Seconds to wait between retries (Gemini free-tier ≈ 30–40s)
    """
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            msg = str(e).lower()
            if "429" in msg or "resourceexhausted" in msg:
                logger.warning(f"[RateLimitGuard] Hit Gemini quota (attempt {attempt}/{max_retries}). Waiting {cooldown}s...")
                time.sleep(cooldown)
            else:
                logger.error(f"[RateLimitGuard] Non-rate-limit error: {e}")
                raise
    logger.error("[RateLimitGuard] Max retries exceeded. Falling back to local model.")
    raise RuntimeError("Gemini quota exceeded repeatedly")
