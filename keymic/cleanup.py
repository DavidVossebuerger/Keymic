"""
Text-Cleanup-Modul — extrahiert aus dictationd.py Postprocess-Pipeline.

Public API:
    cleanup(text, mode="normal", *, api_key=None, use_ai=True,
            custom_dict=None, session=None) -> str
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
@dataclass
class CleanupConfig:
    """Minimal-Config fuer die Cleanup-Pipeline (Backend oder Standalone)."""
    remove_fillers: bool = True
    filler_words: list[str] = field(default_factory=list)
    auto_capitalize: bool = True
    auto_punctuate: bool = False
    # AI-Postprocess
    ai_postprocess: bool = True
    ai_model: str = "llama-3.3-70b-versatile"
    ai_endpoint: str = "https://api.groq.com/openai/v1/chat/completions"
    ai_timeout_s: float = 15.0
    ai_custom_dict: list[str] = field(default_factory=list)
    ai_skip_if_clean: bool = True


# ---------------------------------------------------------------------------
# Modus-Prompts (Server-seitig, via POST /v1/cleanup oder Standalone)
# ---------------------------------------------------------------------------
# Default-Prompts fuer die drei bekannten Modi. Kann via register_mode_prompt()
# zur Laufzeit ueberschrieben werden.
MODE_PROMPTS: dict[str, str] = {
    "strukturiert": (
        "Du bist ein Text-Cleanup-Assistent. Der User hat einen Diktat-Text per Sprache erzeugt.\n"
        "Deine Aufgaben:\n"
        "1. Entferne Fuellwoerter: aeh, aehm, also, halt, quasi, sozusagen, irgendwie, so, ja, ne\n"
        "2. Erkenne Self-Correction im Diktat: Phrasen wie 'nee sorry', 'nein, ich meinte', "
        "'aeh wart mal', 'korrektur', 'eigentlich nicht X sondern Y' zeigen, dass der User "
        "seine Aussage korrigiert. Übernehme in diesem Fall nur die korrigierte Version. "
        "Beispiel: 'Ich gehe um 8, also morgen, um 9' -> 'Ich gehe morgen um 9'. "
        "Beispiel: 'gegen 15, nee sorry, 17 Uhr' -> 'gegen 17 Uhr'.\n"
        "3. Strukturiere den Text in sauberen Fliesstext mit klarer Satzgliederung\n"
        "4. Korrigiere Grammatik und Satzbau\n"
        "5. Respektiere diese Eigennamen/Fachbegriffe: {custom_dict}\n"
        "6. Antworte NUR mit dem bereinigten Text, ohne Anfuehrungszeichen, ohne Erklaerung"
    ),
    "formell": (
        "Du bist ein Text-Cleanup-Assistent. Der User hat einen Diktat-Text per Sprache erzeugt.\n"
        "Deine Aufgaben:\n"
        "1. Entferne Fuellwoerter: aeh, aehm, also, halt, quasi, sozusagen, irgendwie, so, ja, ne\n"
        "2. Erkenne Self-Correction im Diktat: Phrasen wie 'nee sorry', 'nein, ich meinte', "
        "'aeh wart mal', 'korrektur', 'eigentlich nicht X sondern Y' zeigen, dass der User "
        "seine Aussage korrigiert. Übernehme in diesem Fall nur die korrigierte Version. "
        "Beispiel: 'Ich gehe um 8, also morgen, um 9' -> 'Ich gehe morgen um 9'. "
        "Beispiel: 'gegen 15, nee sorry, 17 Uhr' -> 'gegen 17 Uhr'.\n"
        "3. Formuliere den Text in einem formellen, professionellen Ton als sauberen Fliesstext\n"
        "4. Korrigiere Grammatik und Satzbau\n"
        "5. Respektiere diese Eigennamen/Fachbegriffe: {custom_dict}\n"
        "6. Antworte NUR mit dem bereinigten Text, ohne Anfuehrungszeichen, ohne Erklaerung"
    ),
}


def register_mode_prompt(mode: str, prompt: str) -> None:
    """Mode-Prompt registrieren ( Backend seites fuellt das)."""
    MODE_PROMPTS[mode] = prompt


# ---------------------------------------------------------------------------
# Post-Processing
# ---------------------------------------------------------------------------
def postprocess(text: str, cfg: CleanupConfig, *, mode: str = "normal") -> str:
    """Heuristischer Postprocess: Fuellwort-Entfernung, Capitalize, Punctuate.

    Self-Correction (Issue #8) wird NICHT heuristisch aufgeloest, weil
    die Erkennung semantisch ist (was ist KONTEXT, was ist FALSCH). Die
    AI-Postprocess-Stufe kuemmert sich darum — siehe _AI_SYSTEM_TEMPLATE.
    """
    if not text:
        return ""
    out = text

    if cfg.remove_fillers and cfg.filler_words:
        norm = out.lower()
        for w in cfg.filler_words:
            norm = re_sub_word(norm, w.lower())
        out = norm

    # Mehrfach-Spaces / Newlines auf einen Space
    out = " ".join(out.split())

    if cfg.auto_capitalize and out:
        out = out[0].upper() + out[1:]
    if cfg.auto_punctuate and out and out[-1] not in ".!?":
        out += "."
    return out


# Heuristik: natuerliche Sprache enthaelt fast immer Kommas und ist laenger
# als 120 Zeichen. AI lohnt sich dann. Saubere kurze Nominalphrasen ("Berlin
# ist die Hauptstadt") werden weiterhin uebersprungen.
def _looks_like_natural_speech(text: str, filler_words: list[str]) -> bool:
    if not text:
        return False
    norm = text.lower()
    # (a) klassisches Fuellwort
    for w in filler_words:
        if re_sub_word(norm, w.lower()) != norm:
            return True
    # (b) Komma -> typischerweise mehrteiliger Satz
    if "," in text:
        return True
    # (c) laengerer Text -> Grammatik-Cleanup lohnt
    if len(text) > 120:
        return True
    return False


GROQ_CHAT_URL_DEFAULT = "https://api.groq.com/openai/v1/chat/completions"
_AI_SYSTEM_TEMPLATE = (
    "Du bist ein Text-Cleanup-Assistent. Der User hat einen Diktat-Text per Sprache erzeugt.\n"
    "Deine Aufgaben:\n"
    "1. Entferne Fuellwoerter: aeh, aehm, also, halt, quasi, sozusagen, irgendwie, so, ja, ne\n"
    "2. Erkenne Self-Correction im Diktat: Phrasen wie 'nee sorry', 'nein, ich meinte', "
    "'aeh wart mal', 'korrektur', 'eigentlich nicht X sondern Y' zeigen, dass der User "
    "seine Aussage korrigiert. Übernehme in diesem Fall nur die korrigierte Version. "
    "Beispiel: 'Ich gehe um 8, also morgen, um 9' -> 'Ich gehe morgen um 9'. "
    "Beispiel: 'gegen 15, nee sorry, 17 Uhr' -> 'gegen 17 Uhr'.\n"
    "3. Packe den Text als sauberen Fliesstext (nicht 1:1-Wiedergabe)\n"
    "4. Korrigiere Grammatik und Satzbau\n"
    "5. Respektiere diese Eigennamen/Fachbegriffe: {custom_dict}\n"
    "6. Antworte NUR mit dem bereinigten Text, ohne Anfuehrungszeichen, ohne Erklaerung"
)


def ai_postprocess(
    text: str,
    cfg: CleanupConfig,
    api_key: str,
    *,
    session: Optional["requests.Session"] = None,
    stats: Optional[dict] = None,
    override_text: Optional[str] = None,
    system_prompt_override: Optional[str] = None,
) -> str:
    """Optionaler Llama-Postprocess via Groq.

    `text` ist der Text, an dem die Skip-Heuristik prueft (typisch: ROH
    nach Whisper). `override_text` (optional) ist der Text, der
    zurueckgegeben wird, wenn AI uebersprungen wird (typisch: regex-
    bereinigt). So bleibt die Pipeline korrekt: AI bekommt zum Saeubern
    den Originaltext, aber wenn wir aus Latenz-Gruenden skippen, geht der
    bereits regex-bereinigte Output weiter.

    Bei ai_skip_if_clean=True wird der Call uebersprungen, wenn der Text
    keine Filler enthaelt (Heuristik). Bei Netzwerk-/API-Fehler: Fallback
    auf override_text oder text (fail-open).
    """
    fallback = override_text if override_text is not None else text
    if not text or not cfg.ai_postprocess:
        if stats is not None:
            stats["skipped"] = stats.get("skipped", 0) + 1
        return fallback
    if cfg.ai_skip_if_clean and cfg.filler_words and not _looks_like_natural_speech(text, cfg.filler_words):
        if stats is not None:
            stats["skipped"] = stats.get("skipped", 0) + 1
        return fallback
    sess = session or requests
    if system_prompt_override:
        system = system_prompt_override
    else:
        system = _AI_SYSTEM_TEMPLATE.format(
            custom_dict=", ".join(cfg.ai_custom_dict) if cfg.ai_custom_dict else "(keine)"
        )
    try:
        r = sess.post(
            cfg.ai_endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": cfg.ai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.0,
                "max_tokens": 1024,
            },
            timeout=cfg.ai_timeout_s,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Groq chat {r.status_code}: {r.text[:200]}")
        out = r.json()["choices"][0]["message"]["content"].strip()
        if stats is not None:
            stats["ai_calls"] = stats.get("ai_calls", 0) + 1
        return out or text
    except Exception as e:
        # Loggen wuerde den Daemon-Log fluten — still fail-open
        if stats is not None:
            stats["ai_errors"] = stats.get("ai_errors", 0) + 1
        return text


def re_sub_word(text: str, word: str) -> str:
    """Ganzwort-Ersetzung (ASCII). Minimal-Implementierung, keine regex-Mod-Dep."""
    out_parts: list[str] = []
    i = 0
    n = len(text)
    L = len(word)
    while i < n:
        if text[i:i + L] == word and _is_word_boundary(text, i, L):
            out_parts.append("")
            i += L
        else:
            out_parts.append(text[i])
            i += 1
    return "".join(out_parts)


def _is_word_boundary(text: str, start: int, length: int) -> bool:
    def is_alnum(c: str) -> bool:
        return c.isalnum()
    left_ok = (start == 0) or not is_alnum(text[start - 1])
    end = start + length
    right_ok = (end >= len(text)) or not is_alnum(text[end])
    return left_ok and right_ok


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def cleanup(
    text: str,
    mode: str = "normal",
    *,
    api_key: Optional[str] = None,
    use_ai: bool = True,
    custom_dict: Optional[list[str]] = None,
    session: Optional["requests.Session"] = None,
) -> str:
    """oeffentliche Cleanup-API.

    Args:
        text: Rohtext (z.B. Whisper-Output).
        mode: Cleanup-Modus ("normal", "strukturiert", "formell", …).
              Steuert den AI-System-Prompt.
        api_key: Groq-API-Key fuer AI-Postprocess.
        use_ai: AI-Postprocess aktivieren (sonst nur Heuristik).
        custom_dict: Liste von Eigennamen/Fachbegriffen, die erhalten bleiben.
        session: Optionaler requests.Session fuer Connection-Pooling.

    Returns:
        Bereinigter Text.
    """
    cfg = CleanupConfig(
        # remove_fillers=False: User-Wunsch — Füllwörter wie "so", "halt",
        # "quasi" etc. sollen erhalten bleiben, nicht abgeschnitten werden.
        # Whitespace/Capitalize/Punctuate laufen weiterhin.
        remove_fillers=False,
        filler_words=["aehm", "halt", "quasi", "also", "ja", "ne", "so", "irgendwie"],
        auto_capitalize=True,
        auto_punctuate=True,
        ai_postprocess=use_ai,
        ai_custom_dict=custom_dict or [],
    )

    # Heuristik
    cleaned = postprocess(text, cfg, mode=mode)
    if not use_ai or not api_key:
        return cleaned

    # Mode-spezifischer Prompt
    system_prompt = None
    if mode != "normal" and mode in MODE_PROMPTS:
        system_prompt = MODE_PROMPTS[mode]

    return ai_postprocess(
        text,
        cfg,
        api_key,
        session=session,
        override_text=cleaned,
        system_prompt_override=system_prompt,
    )
