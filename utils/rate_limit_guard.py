import time
import logging

from monitoring.metrics import (
    record_gemini_failure,   # increments failure counters
    GEMINI_CALLS,            # per-module call counter
)

logger = logging.getLogger("rate_limit_guard")


def rate_limit_safe_call(
    func,
    *args,
    module_name="unknown",        # filtering / summarization / response
    max_retries=3,
    cooldown=35,
    backoff_factor=1.4,
    **kwargs
):
    """
    Unified safe executor for Gemini API calls.
    Handles:
        • 429 / quota / rate-limits
        • Exponential backoff
        • Module-level Prometheus metrics
        • Clean propagation of non-rate-limit errors

    Parameters:
        func: The Gemini model.invoke function
        module_name: classifier for Prometheus (filtering/summarization/response)
        max_retries: attempts before failing
        cooldown: initial wait time for a rate-limit
        backoff_factor: multiplier for exponential backoff
    """

    # Count every Gemini API call
    GEMINI_CALLS.labels(module=module_name).inc()

    wait_time = cooldown

    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)

        except Exception as e:
            err = str(e).lower()

            # Detect all known rate-limit / quota signals
            rate_limited = any(
                token in err for token in [
                    "429",
                    "quota",
                    "rate limit",
                    "exceeded",
                    "resourceexhausted",
                    "too many requests",
                    "exhausted",
                ]
            )

            # ------------------------------------------------------------
            # RATE-LIMIT HANDLING
            # ------------------------------------------------------------
            if rate_limited:
                record_gemini_failure(module_name, reason="rate_limit")

                if attempt < max_retries:
                    logger.warning(
                        f"[RateLimitGuard] {module_name}: Rate limit hit "
                        f"(attempt {attempt}/{max_retries}). Waiting {wait_time}s…"
                    )
                    time.sleep(wait_time)
                    wait_time = int(wait_time * backoff_factor)
                    continue

                logger.error(
                    f"[RateLimitGuard] {module_name}: Max retries exceeded (quota)."
                )
                raise RuntimeError("Gemini quota exceeded repeatedly") from e

            # ------------------------------------------------------------
            # NON-RATE-LIMIT ERRORS — propagate immediately
            # ------------------------------------------------------------
            logger.error(
                f"[RateLimitGuard] {module_name}: Non-rate-limit Gemini error: {e}"
            )

            record_gemini_failure(module_name, reason="other_error")
            raise

    # If loop exits unexpectedly (should not happen)
    raise RuntimeError("RateLimitGuard: Unexpected retry exhaustion")
