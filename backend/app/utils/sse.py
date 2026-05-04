"""
sse.py - Server-Sent Events helpers shared across API routers.

Centralises the SSE message formatting function and the queue sentinel
used by both the download and music job routers.
"""

#: Sentinel pushed onto a job queue to signal stream completion.
SSE_JOB_DONE: str = "__JOB_DONE__"


def sse_pack(data: str, event: str | None = None) -> str:
    """Format *data* as an SSE message block.

    Args:
        data: The payload string (may contain newlines).
        event: Optional SSE event name; omit for anonymous ``data:`` frames.

    Returns:
        A complete SSE message block ending with a blank line.
    """
    payload = "".join(f"data: {line}\n" for line in data.splitlines()) or "data: \n"
    prefix = f"event: {event}\n" if event else ""
    return prefix + payload + "\n"
