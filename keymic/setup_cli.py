"""Interaktives Setup: API-Key, Hotkey, Injection, Sprache, Vokabular."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from keymic.config import default_config, save_config


HOTKEY_CHOICES = [
    ("Right Ctrl (default)", "KEY_RIGHTCTRL"),
    ("Right Alt", "KEY_RIGHTALT"),
    ("Right Shift", "KEY_RIGHTSHIFT"),
    ("F12", "KEY_F12"),
    ("Pause", "KEY_PAUSE"),
    ("Play/Pause", "KEY_PLAYPAUSE"),
]

INJECTION_CHOICES = [
    ("auto (empfohlen)", "auto"),
    ("ydotool (Wayland)", "ydotool"),
    ("xdotool (X11)", "xdotool"),
    ("clipboard", "clipboard"),
]

LANGUAGE_CHOICES = [
    ("Auto-Detect", "auto"),
    ("Deutsch", "de"),
    ("English", "en"),
]


def _prompt(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{question}{suffix}: ").strip()
    return val if val else default


def _select(question: str, choices: list, default_idx: int = 0) -> str:
    print(question)
    for i, (label, _) in enumerate(choices):
        marker = " *" if i == default_idx else "  "
        print(f"  {marker}{i+1}. {label}")
    raw = _prompt(f"Auswahl (1-{len(choices)})", str(default_idx + 1))
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(choices):
            return choices[idx][1]
    except ValueError:
        pass
    return choices[default_idx][1]


def _validate_groq_key(key: str) -> bool:
    """Quick API-Call to validate. Accepts on network failure (warns)."""
    if not key or not key.startswith("gsk_"):
        return False
    if not shutil.which("curl"):
        # Can't validate; trust the format check
        return True
    try:
        r = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
             "-H", f"Authorization: Bearer {key}",
             "https://api.groq.com/openai/v1/models"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() == "200"
    except Exception:
        print("Warnung: API-Key konnte nicht validiert werden (Netzwerk?). "
              "Wird trotzdem gespeichert.")
        return True


def _select_hotkey() -> str:
    print()
    print("Welcher Hotkey soll die Aufnahme starten/stoppen?")
    for i, (label, value) in enumerate(HOTKEY_CHOICES):
        print(f"  {i+1}. {label} ({value})")
    print(f"  {len(HOTKEY_CHOICES)+1}. Custom (z. B. KEY_X)")
    raw = _prompt("Auswahl", "1")
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(HOTKEY_CHOICES):
            return HOTKEY_CHOICES[idx][1]
        if idx == len(HOTKEY_CHOICES):
            custom = _prompt("Custom-Key (z. B. KEY_F13)")
            return custom.upper()
    except ValueError:
        pass
    return HOTKEY_CHOICES[0][1]


def _select_injection() -> str:
    print()
    print("Wie soll der Text eingefügt werden?")
    return _select("Methode", INJECTION_CHOICES, default_idx=0)


def _select_language() -> str:
    print()
    print("Welche Sprache soll erkannt werden?")
    return _select("Sprache", LANGUAGE_CHOICES, default_idx=0)


def _ask_vocab() -> list[str]:
    print()
    raw = _prompt("Eigennamen/Fachbegriffe (optional, komma-getrennt)", "")
    if not raw:
        return []
    return [w.strip() for w in raw.split(",") if w.strip()]


def run_setup(*, config_path: Optional[Path] = None, force: bool = False) -> int:
    """Interactive setup flow. Returns exit code."""
    if config_path is None:
        from keymic.config import DEFAULT_CONFIG_PATH
        config_path = DEFAULT_CONFIG_PATH
    if config_path.exists() and not force:
        print(f"Config existiert bereits: {config_path}")
        if _prompt("Überschreiben? (j/n)", "n").lower() not in ("j", "y", "yes"):
            print("Abgebrochen.")
            return 1

    print("=" * 60)
    print(" Keymic Setup")
    print("=" * 60)
    print()
    print("Du brauchst einen Groq API-Key. Hole ihn dir hier:")
    print("  https://console.groq.com/keys")
    print()
    api_key = _prompt("Groq API-Key")
    if not api_key:
        print("Fehler: API-Key ist erforderlich.")
        return 1
    if not _validate_groq_key(api_key):
        print("Fehler: API-Key ungültig (sollte mit 'gsk_' anfangen).")
        return 1

    hotkey = _select_hotkey()
    injection = _select_injection()
    language = _select_language()
    vocab = _ask_vocab()

    cfg = default_config()
    # api_key is NOT saved to TOML; user should set GROQ_API_KEY env var instead
    cfg["general"]["hotkey"] = hotkey
    cfg["general"]["language"] = language
    cfg["injection"]["method"] = injection
    if vocab:
        cfg["groq"]["vocab"] = vocab
        cfg["groq"]["prompt"] = "Eigennamen: " + ", ".join(vocab)

    save_config(cfg, config_path)
    print()
    print(f"Config gespeichert: {config_path}")
    print()
    print("Setze deinen API-Key als Umgebungsvariable:")
    print(f"  export GROQ_API_KEY={api_key}")
    print()

    # Install-Mode fragen
    install_choice = _ask_install_mode(Path.cwd())
    if install_choice == "skip":
        pass
    else:
        rc = _run_pip_install(install_choice, Path.cwd())
        if rc != 0:
            print("Installation fehlgeschlagen. Config ist trotzdem gespeichert.")
            print("Du kannst sie manuell installieren mit:")
            print(f"  cd {Path.cwd()} && pip install --user -e .")
            return rc

    print()
    print("Fertig! Starte den Daemon mit:")
    if install_choice == "user":
        print("  keymic run           # global verfügbar nach Reload von ~/.bashrc")
        print("  # oder")
        print("  python -m keymic run # funktioniert jetzt überall")
    elif install_choice == "system":
        print("  keymic run           # systemweit verfügbar")
    else:
        print(f"  python -m keymic run # nur aus {Path.cwd()} heraus")
    return 0


def _ask_install_mode(source_dir: Path) -> str:
    """Fragt nach Installations-Modus. Returns: user|system|skip."""
    if not (source_dir / "pyproject.toml").exists():
        print("Hinweis: pyproject.toml nicht im aktuellen Verzeichnis gefunden —")
        print(f"  {source_dir}")
        print("Installation übersprungen. Starte setup aus dem Repo-Root.")
        return "skip"

    print()
    print("Wie soll keymic installiert werden?")
    print("  1. User-Install (empfohlen): pip install --user")
    print("     → 'keymic' ist verfügbar in ~/.local/bin")
    print("  2. System-Install: sudo pip install")
    print("     → 'keymic' ist systemweit verfügbar")
    print("  3. Skip: Nur Config schreiben, keine Installation")
    print("     → Nutzung nur aus diesem Verzeichnis oder per venv")
    raw = _prompt("Auswahl (1-3)", "1")
    if raw == "2":
        return "system"
    if raw == "3":
        return "skip"
    return "user"


def _run_pip_install(mode: str, cwd: Path) -> int:
    """Run pip install --user or sudo pip install."""
    if mode == "user":
        cmd = ["pip", "install", "--user", "-e", "."]
        print(f"Führe aus: {' '.join(cmd)} (in {cwd})")
        try:
            r = subprocess.run(cmd, cwd=cwd, check=False)
            if r.returncode != 0:
                return r.returncode
            print("Installation erfolgreich.")
            print("Hinweis: ~/.local/bin muss in PATH sein.")
            print("  echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc")
            return 0
        except FileNotFoundError:
            print("Fehler: 'pip' nicht gefunden. Installiere manuell mit:")
            print(f"  cd {cwd} && python3 -m pip install --user -e .")
            return 1
    if mode == "system":
        cmd = ["sudo", "pip", "install", "-e", "."]
        print(f"Führe aus: {' '.join(cmd)} (in {cwd})")
        try:
            r = subprocess.run(cmd, cwd=cwd, check=False)
            if r.returncode != 0:
                return r.returncode
            print("System-Installation erfolgreich.")
            return 0
        except FileNotFoundError:
            print("Fehler: 'sudo' oder 'pip' nicht gefunden.")
            return 1
    return 0
