class ProviderError(Exception):
    """Raised when a search provider fails after all retries. Caller
    decides whether that's fatal (all providers down) or tolerable
    (one of several)."""
