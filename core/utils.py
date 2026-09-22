"""Shared utility functions for the IP-SAKTI Sahayak project."""


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max_length and add ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + '...'
