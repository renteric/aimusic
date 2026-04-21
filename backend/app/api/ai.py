"""
ai.py - Claude AI intelligence layer for AI-Music.

Routes registered under the ``/api/ai`` prefix:

    POST /api/ai/cleanup    — clean and correct a raw Whisper transcript
    POST /api/ai/analyse    — analyse a song from its transcript
    POST /api/ai/tags       — generate structured genre/mood/energy tags
    POST /api/ai/translate  — translate song lyrics to a target language
"""

import json
import re
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.auth import get_current_user  # noqa: F401 — used via require_roles
from ..core.config import AppConfig
from ..core.roles import require_roles
from ..models.user import User
from ..utils.files import safe_media_path

router = APIRouter(prefix="/api/ai", tags=["ai"])

#: Claude model used for all AI endpoints.
_MODEL = "claude-sonnet-4-6"
#: Generous token budget — analyses can be detailed.
_MAX_TOKENS = 4096


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_client() -> anthropic.Anthropic:
    """Return an Anthropic client, or raise 503 if the key is not configured.

    Returns:
        Configured :class:`anthropic.Anthropic` instance.

    Raises:
        HTTPException: 503 when ``ANTHROPIC_API_KEY`` is not set.
    """
    if not AppConfig.ANTHROPIC_API_KEY:
        raise HTTPException(503, "AI features are not configured (ANTHROPIC_API_KEY not set).")
    return anthropic.Anthropic(api_key=AppConfig.ANTHROPIC_API_KEY)


def _call_claude(client: anthropic.Anthropic, prompt: str) -> str:
    """Send a single-turn prompt to Claude and return the text response.

    Args:
        client: Authenticated Anthropic client.
        prompt: User-turn message text.

    Returns:
        Plain text from Claude's first content block.

    Raises:
        HTTPException: 502 on any Anthropic API error.
    """
    try:
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except anthropic.APIStatusError as exc:
        # 400 content-filtering block — surface as 422 so the UI can show a clear message.
        if exc.status_code == 400 and "content filtering policy" in str(exc.message).lower():
            raise HTTPException(
                422,
                "The content of this file was blocked by the AI content filtering policy. "
                "Try a different file.",
            ) from exc
        raise HTTPException(502, f"Claude API error: {exc.message}") from exc
    except Exception as exc:
        raise HTTPException(502, f"Claude API error: {exc}") from exc


def _read_transcript(target: Path) -> str:
    """Read and validate a Markdown transcript file.

    Args:
        target: Absolute path to the ``.md`` transcript file.

    Returns:
        Non-empty transcript text.

    Raises:
        HTTPException: 404 if the file does not exist, 422 if it is empty.
    """
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Transcript file not found.")
    text = target.read_text(encoding="utf-8").strip()
    if not text:
        raise HTTPException(422, "Transcript file is empty.")
    return text


def _resolve_transcript_path(target: Path) -> Path:
    """Resolve the expected transcript path for a given media file.

    For ``.md`` files the path is returned as-is.  For audio files the
    conventional sibling ``<filename>.md`` is returned.

    Args:
        target: Absolute path to an audio file or its transcript.

    Returns:
        Absolute path to the expected transcript ``.md`` file.

    Raises:
        HTTPException: 422 if the target is an audio file with no transcript.
    """
    if target.suffix.lower() == ".md":
        return target
    sibling = target.parent / (target.name + ".md")
    if not sibling.exists():
        raise HTTPException(
            422,
            "No transcript found for this file. Transcribe the audio first.",
        )
    return sibling


def _read_transcript_optional(target: Path) -> str:
    """Return the transcript text for *target*, or an empty string if absent.

    Unlike :func:`_resolve_transcript_path`, this never raises — the tags
    endpoint can still produce useful output from the filename alone.

    Args:
        target: Absolute path to an audio file or its ``.md`` transcript.

    Returns:
        Transcript text, or ``""`` if no transcript file exists.
    """
    if target.suffix.lower() == ".md":
        text = target.read_text(encoding="utf-8").strip() if target.exists() else ""
        return text
    sibling = target.parent / (target.name + ".md")
    if sibling.exists():
        return sibling.read_text(encoding="utf-8").strip()
    return ""


def _parse_claude_json(raw: str) -> dict:
    """Extract and parse a JSON object from a Claude response string.

    Claude sometimes wraps its JSON output in a Markdown code fence
    (````json ... ````).  This helper handles both cases.

    Args:
        raw: Raw text returned by Claude.

    Returns:
        Parsed dictionary.

    Raises:
        HTTPException: 502 when the response cannot be parsed as JSON.
    """
    # Strip optional ```json ... ``` or ``` ... ``` fence.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else raw.strip()

    # Trim any leading/trailing non-JSON characters.
    start = candidate.find("{")
    end = candidate.rfind("}") + 1
    if start == -1 or end == 0:
        raise HTTPException(502, f"Claude returned non-JSON output: {raw[:200]}")
    try:
        return json.loads(candidate[start:end])
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Could not parse Claude JSON: {exc}") from exc


# ── Endpoints ─────────────────────────────────────────────────────────────────


class CleanupBody(BaseModel):
    """Request body for POST /api/ai/cleanup."""

    path: str
    save: bool = False


@router.post("/cleanup")
def cleanup_transcript(
    body: CleanupBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Clean and correct a raw Whisper speech-to-text transcript using Claude.

    Fixes punctuation, capitalisation, and obvious mis-heard words, then
    groups lines into labelled song sections (Verse, Chorus, Bridge …).

    Args:
        body: JSON body with ``path`` (must be a ``.md`` file) and optional
              ``save`` flag to overwrite the source file with the cleaned text.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "cleaned": str, "path": str}``.

    Raises:
        HTTPException: 404 if the file does not exist, 422 if it is not a
            ``.md`` file or is empty, 502/503 on AI errors.
    """
    target = safe_media_path(body.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")
    if target.suffix.lower() != ".md":
        raise HTTPException(422, "Path must point to a .md transcript file.")

    raw = _read_transcript(target)
    client = _get_client()

    prompt = (
        "You are a professional music transcription editor.\n\n"
        "Below is a raw Whisper speech-to-text transcript of a song. "
        "Please clean it up:\n"
        "- Fix punctuation and capitalisation\n"
        "- Correct obvious mis-heard words (use musical and linguistic context)\n"
        "- Group text into clearly separated sections using blank lines\n"
        "- Label each section (e.g. [Intro], [Verse 1], [Chorus], [Bridge], [Outro]) "
        "when the structure is identifiable\n"
        "- Do NOT translate — keep the original language\n"
        "- Return only the cleaned transcript, no explanations or commentary\n\n"
        f"RAW TRANSCRIPT:\n{raw}"
    )

    cleaned = _call_claude(client, prompt)

    if body.save:
        target.write_text(cleaned, encoding="utf-8")

    return {"success": True, "cleaned": cleaned, "path": body.path}


class AnalyseBody(BaseModel):
    """Request body for POST /api/ai/analyse."""

    path: str
    save: bool = False


@router.post("/analyse")
def analyse_song(
    body: AnalyseBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Analyse a song's structure, themes, and lyrical devices via Claude.

    Accepts either an audio file path (looks for a sibling ``.md`` transcript)
    or a transcript ``.md`` path directly.

    Args:
        body: JSON body with ``path`` and optional ``save`` flag.  When
              ``save=True`` the analysis is written to a sibling
              ``<name>.analysis.md`` file inside the media directory.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "analysis": str, "saved_path": str | None, "path": str}``.

    Raises:
        HTTPException: 404 if the file does not exist, 422 if no transcript is
            found for an audio file, 502/503 on AI errors.
    """
    target = safe_media_path(body.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")

    transcript_path = _resolve_transcript_path(target)
    transcript = _read_transcript(transcript_path)

    # Use the stem (without extension) as the song name hint for Claude.
    song_name = target.stem if target.suffix.lower() != ".md" else Path(target.stem).stem

    client = _get_client()

    prompt = (
        "You are a professional music analyst and songwriter.\n\n"
        "Analyse the following song transcript and provide a detailed analysis.\n\n"
        f"**Song name / filename:** {song_name}\n\n"
        f"**TRANSCRIPT:**\n{transcript}\n\n"
        "Please provide a Markdown-formatted analysis with these sections:\n\n"
        "### Song Structure\n"
        "Identify and label each section (Intro, Verse 1, Pre-Chorus, Chorus, "
        "Verse 2, Bridge, Outro, etc.) with the opening line of each.\n\n"
        "### Theme & Mood\n"
        "Main emotional themes, mood, and overall tone.\n\n"
        "### Lyrical Devices\n"
        "Rhyme scheme, metaphors, alliteration, repetition, and notable imagery.\n\n"
        "### Key Lines\n"
        "The most memorable or meaningful lines, with a brief note on why.\n\n"
        "### Overall Assessment\n"
        "A concise paragraph on the song's style, artistic intent, and impact."
    )

    analysis = _call_claude(client, prompt)

    saved_path: str | None = None
    if body.save:
        if target.suffix.lower() == ".md":
            # e.g. song.mp3.md  →  song.mp3.analysis.md
            save_target = target.with_suffix(".analysis.md")
        else:
            # e.g. song.mp3  →  song.mp3.analysis.md
            save_target = target.parent / (target.name + ".analysis.md")
        save_target.write_text(analysis, encoding="utf-8")
        saved_path = save_target.relative_to(AppConfig.MEDIA_DIR).as_posix()

    return {
        "success": True,
        "analysis": analysis,
        "saved_path": saved_path,
        "path": body.path,
    }


class TagsBody(BaseModel):
    """Request body for POST /api/ai/tags."""

    path: str
    save: bool = False


@router.post("/tags")
def generate_tags(
    body: TagsBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Generate structured metadata tags for a media file using Claude.

    Accepts an audio file path or a ``.md`` transcript path.  When a transcript
    exists it is included in the prompt for richer results; when absent Claude
    falls back to the filename alone.

    Tag fields returned:

    - ``genre``       — list of genre labels (e.g. ``["Pop", "Electronic"]``)
    - ``mood``        — list of mood descriptors (e.g. ``["melancholic", "hopeful"]``)
    - ``energy``      — one of ``"low"``, ``"medium"``, ``"high"``
    - ``tempo``       — one of ``"slow"``, ``"moderate"``, ``"fast"``
    - ``themes``      — list of lyrical/narrative themes
    - ``instruments`` — list of instruments detected or implied
    - ``language``    — detected language of the lyrics (``"unknown"`` when absent)
    - ``tags``        — flat list of all searchable terms (union of all fields)

    When ``save=True`` the tags are written to a sibling ``<name>.tags.json``
    file inside the media directory.

    Args:
        body: JSON body with ``path`` and optional ``save`` flag.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "tags": dict, "saved_path": str | None, "path": str}``.

    Raises:
        HTTPException: 404 if the file does not exist, 502/503 on AI errors.
    """
    target = safe_media_path(body.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")

    transcript = _read_transcript_optional(target)
    song_name = target.stem if target.suffix.lower() != ".md" else Path(target.stem).stem

    transcript_section = (
        f"\n\nLYRIC TRANSCRIPT (excerpt — use for language/theme/mood detection):\n{transcript[:3000]}"
        if transcript
        else "\n\n(No transcript available — infer from the filename only.)"
    )

    client = _get_client()

    prompt = (
        "You are a music metadata expert. Generate accurate, searchable tags for a song.\n\n"
        f"FILENAME: {song_name}{transcript_section}\n\n"
        "Return ONLY a valid JSON object — no explanation, no Markdown, no code fence — "
        "with exactly these fields:\n\n"
        '{\n'
        '  "genre": ["<genre1>", "<genre2>"],\n'
        '  "mood": ["<mood1>", "<mood2>"],\n'
        '  "energy": "<low|medium|high>",\n'
        '  "tempo": "<slow|moderate|fast>",\n'
        '  "themes": ["<theme1>", "<theme2>"],\n'
        '  "instruments": ["<instrument1>", "<instrument2>"],\n'
        '  "language": "<language or unknown>",\n'
        '  "tags": ["<flat searchable tag1>", "<flat searchable tag2>", ...]\n'
        "}\n\n"
        "Rules:\n"
        "- genre: 1–3 labels, capitalised (e.g. Pop, Hip-Hop, Jazz)\n"
        "- mood: 2–5 lowercase adjectives (e.g. melancholic, uplifting)\n"
        "- energy: exactly one of low / medium / high\n"
        "- tempo: exactly one of slow / moderate / fast\n"
        "- themes: 2–5 narrative themes (e.g. heartbreak, resilience, nostalgia)\n"
        "- instruments: 2–6 instruments (e.g. guitar, piano, synthesizer)\n"
        "- language: full language name in English (e.g. Spanish, English, French)\n"
        "- tags: 8–15 unique lowercase terms covering genre, mood, themes, instruments\n"
        "- If unsure, make a reasonable inference — never leave a list empty"
    )

    raw = _call_claude(client, prompt)
    tags = _parse_claude_json(raw)

    # Normalise energy and tempo to known values (guard against hallucination).
    _ENERGY_VALUES = {"low", "medium", "high"}
    _TEMPO_VALUES = {"slow", "moderate", "fast"}
    if tags.get("energy") not in _ENERGY_VALUES:
        tags["energy"] = "medium"
    if tags.get("tempo") not in _TEMPO_VALUES:
        tags["tempo"] = "moderate"

    saved_path: str | None = None
    if body.save:
        if target.suffix.lower() == ".md":
            save_target = target.with_suffix(".tags.json")
        else:
            save_target = target.parent / (target.name + ".tags.json")
        save_target.write_text(json.dumps(tags, ensure_ascii=False, indent=2), encoding="utf-8")
        saved_path = save_target.relative_to(AppConfig.MEDIA_DIR).as_posix()

    return {
        "success": True,
        "tags": tags,
        "saved_path": saved_path,
        "path": body.path,
    }


class TranslateBody(BaseModel):
    """Request body for POST /api/ai/translate."""

    path: str
    target_language: str
    save: bool = False


@router.post("/translate")
def translate_lyrics(
    body: TranslateBody,
    current_user: User = Depends(require_roles("superadmin", "admin", "user")),
) -> dict:
    """Translate song lyrics to a target language using Claude.

    Accepts an audio file path (looks for a sibling ``.md`` transcript) or a
    transcript ``.md`` path directly.  The translation preserves the original
    song structure (section labels, blank-line separators) and adds cultural
    notes inline for phrases that resist direct translation.

    When ``save=True`` the result is written to a sibling file named
    ``<stem>.<lang_slug>.translation.md`` inside the media directory.

    Args:
        body: JSON body with ``path``, ``target_language`` (e.g. ``"French"``),
              and optional ``save`` flag.
        current_user: Resolved by the role dependency.

    Returns:
        ``{"success": bool, "translation": str, "saved_path": str | None,
        "path": str, "target_language": str}``.

    Raises:
        HTTPException: 400 if ``target_language`` is blank or too long.
            404 if the file does not exist.  422 if no transcript is found.
            502/503 on AI errors.
    """
    lang = body.target_language.strip()
    if not lang:
        raise HTTPException(400, "target_language must not be empty.")
    if len(lang) > 60:
        raise HTTPException(400, "target_language is too long.")

    target = safe_media_path(body.path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found.")

    transcript_path = _resolve_transcript_path(target)
    transcript = _read_transcript(transcript_path)

    # Derive a short file-safe slug from the language name for save path.
    lang_slug = re.sub(r"[^a-z0-9]", "", lang.lower())[:12]

    # Use the stem (without extension) as the song name hint.
    song_name = target.stem if target.suffix.lower() != ".md" else Path(target.stem).stem

    client = _get_client()

    prompt = (
        "You are a professional lyric translator with expertise in poetry and music.\n\n"
        f"Translate the following song lyrics into **{lang}**.\n\n"
        f"**Song name / filename:** {song_name}\n\n"
        "**ORIGINAL LYRICS:**\n"
        f"{transcript}\n\n"
        "Translation guidelines:\n"
        "- Preserve the original song structure exactly: keep section labels such as "
        "[Intro], [Verse 1], [Chorus], [Bridge], etc. unchanged\n"
        "- Keep blank lines between sections\n"
        "- Aim for a natural, singable, poetic translation — not a word-for-word literal one\n"
        "- Maintain rhyme and metre where possible without sacrificing meaning\n"
        "- For idioms or culturally specific phrases that don't translate directly, "
        "provide the best equivalent and add a brief note in italics on the next line, "
        "e.g. *[Translator's note: the original phrase means ...]*\n"
        "- Return only the translated lyrics and any inline notes — no preamble, "
        "no commentary, no explanations outside the notes"
    )

    translation = _call_claude(client, prompt)

    saved_path: str | None = None
    if body.save:
        if target.suffix.lower() == ".md":
            save_target = target.parent / (target.stem + f".{lang_slug}.translation.md")
        else:
            save_target = target.parent / (target.name + f".{lang_slug}.translation.md")
        save_target.write_text(translation, encoding="utf-8")
        saved_path = save_target.relative_to(AppConfig.MEDIA_DIR).as_posix()

    return {
        "success": True,
        "translation": translation,
        "saved_path": saved_path,
        "path": body.path,
        "target_language": lang,
    }
