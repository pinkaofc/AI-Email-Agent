import time
import logging

logger = logging.getLogger("rate_limit_guard")


def rate_limit_safe_call(
    func,
    *args,
    max_retries=3,
    cooldown=35,
    backoff_factor=1.4,
    **kwargs
):
    """
    Executes an API call safely with:
      - Built-in Gemini 429 / quota handling
      - Gradual exponential backoff
      - Clean error propagation for non-rate-limit errors
      - Safe fallback after exhaustion

    Args:
        func: Callable API function (Gemini or LangChain wrapped call)
        *args, **kwargs: Passed to the function
        max_retries: Total retry attempts
        cooldown: Initial wait after 429 / quota
        backoff_factor: Cooldown multiplier per retry (e.g., 35s → 49s → 68s)
    """

    wait_time = cooldown

    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)

        except Exception as e:
            error_text = str(e).lower()

            is_rate_limit = (
                "429" in error_text
                or "quota" in error_text
                or "resourceexhausted" in error_text
                or "rate limit" in error_text
                or "exceeded" in error_text
            )

            # ------------------------------------------------------------
            # Handle rate-limit / quota errors (Gemini specific)
            # ------------------------------------------------------------
            if is_rate_limit:
                if attempt < max_retries:
                    logger.warning(
                        f"[RateLimitGuard] Gemini rate limit hit "
                        f"(attempt {attempt}/{max_retries}). "
                        f"Sleeping for {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    wait_time = int(wait_time * backoff_factor)
                    continue
                else:
                    logger.error("[RateLimitGuard] Max retries exceeded due to quota/429.")
                    raise RuntimeError("Gemini quota exceeded repeatedly") from e

            # ------------------------------------------------------------
            # Non-rate-limit errors → propagate immediately
            # ------------------------------------------------------------
            logger.error(f"[RateLimitGuard] Non-rate-limit error: {e}")
            raise

    # This line should almost never be reached; defensive fallback
    raise RuntimeError("RateLimitGuard exhausted retries unexpectedly")
