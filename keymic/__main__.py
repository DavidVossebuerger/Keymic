"""CLI entry point. Routes subcommands."""
import argparse
import os
import signal
import sys
import time
from pathlib import Path

from keymic import __version__
from keymic.config import load_config, DEFAULT_CONFIG_PATH


def _state_dir() -> Path:
    """PID + Log files location. HOME-relative (sandbox-friendly).

    Bewusst NICHT XDG_RUNTIME_DIR-basiert: PipeWire und viele andere
    Audio-Stacks brauchen den echten XDG_RUNTIME_DIR. Wenn der Wrapper
    ihn überschreibt, brechen pw-cat und Co. Deshalb liegen unsere
    PID/Log-Files unter ~/.local/share/keymic — HOME-Isolation reicht.
    """
    d = Path.home() / ".local" / "share" / "keymic"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_version(_args):
    print(f"keymic {__version__}")


def cmd_setup(args):
    from keymic.setup_cli import run_setup
    return run_setup(force=getattr(args, "force", False)) or 0


def cmd_run(args):
    if getattr(args, "foreground", False):
        _run_foreground()
        return 0
    return _daemonize()


def _run_foreground() -> None:
    from keymic.daemon import DictationDaemon
    cfg = load_config(DEFAULT_CONFIG_PATH)
    DictationDaemon(cfg).run()


def _daemonize() -> int:
    """Double-fork to detach, write PID file, return immediately."""
    pid_file = _state_dir() / "keymic.pid"
    log_file = _state_dir() / "keymic.log"

    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            os.kill(old_pid, 0)
            print(f"Keymic läuft bereits (PID {old_pid}).", file=sys.stderr)
            print(f"Stoppen mit: keymic stop", file=sys.stderr)
            return 1
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)

    # First fork
    pid = os.fork()
    if pid > 0:
        # Parent waits for grandchild to write PID file
        for _ in range(50):
            time.sleep(0.1)
            if pid_file.exists():
                daemon_pid = pid_file.read_text().strip()
                print(f"Keymic gestartet (PID {daemon_pid}).")
                print(f"Log:  {log_file}")
                print(f"Stop: keymic stop")
                return 0
        print("Daemon-Start fehlgeschlagen (kein PID-File nach 5s).", file=sys.stderr)
        return 1

    # Child: detach session, second fork
    os.setsid()
    pid = os.fork()
    if pid > 0:
        os._exit(0)  # intermediate parent exits

    # Grandchild = actual daemon
    _redirect_stdio(log_file)
    pid_file.write_text(str(os.getpid()))

    try:
        _run_foreground()
    except Exception as e:
        with open(log_file, "a") as f:
            import traceback
            traceback.print_exc(file=f)
            f.write(f"\nDaemon crashed: {e}\n")
    finally:
        pid_file.unlink(missing_ok=True)
    os._exit(0)


def _redirect_stdio(log_file: Path) -> None:
    """Detach stdin/stdout/stderr from controlling terminal."""
    with open("/dev/null", "rb") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    with open(log_file, "ab") as logf:
        os.dup2(logf.fileno(), sys.stdout.fileno())
        os.dup2(logf.fileno(), sys.stderr.fileno())
    # Python-Logging an stderr koppeln → landet im log_file
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )


def cmd_stop(_args):
    pid_file = _state_dir() / "keymic.pid"
    if not pid_file.exists():
        print("Keymic läuft nicht.")
        return 1
    pid_str = pid_file.read_text().strip()
    try:
        pid = int(pid_str)
    except ValueError:
        print(f"Ungültige PID-Datei: {pid_str!r}")
        pid_file.unlink(missing_ok=True)
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pid_file.unlink(missing_ok=True)
                print(f"Keymic gestoppt (PID {pid}).")
                return 0
        print(f"PID {pid} reagiert nicht auf SIGTERM — erzwinge SIGKILL", file=sys.stderr)
        os.kill(pid, signal.SIGKILL)
        pid_file.unlink(missing_ok=True)
        return 0
    except ProcessLookupError:
        print(f"PID {pid} nicht aktiv — veraltete PID-Datei entfernt.")
        pid_file.unlink(missing_ok=True)
        return 1


def cmd_status(_args):
    pid_file = _state_dir() / "keymic.pid"
    log_file = _state_dir() / "keymic.log"
    if not pid_file.exists():
        print("Keymic läuft nicht.")
        return 1
    pid_str = pid_file.read_text().strip()
    try:
        pid = int(pid_str)
    except ValueError:
        print(f"Ungültige PID-Datei: {pid_str!r}")
        return 1
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        print(f"veraltete PID-Datei (PID {pid} nicht aktiv).")
        pid_file.unlink(missing_ok=True)
        return 1
    log_size = log_file.stat().st_size if log_file.exists() else 0
    print(f"Keymic läuft (PID {pid}).")
    print(f"Log: {log_file} ({log_size} bytes)")
    return 0


def cmd_check(_args):
    """Diagnose environment: API key, hotkey device, audio device, injection backend."""
    import shutil
    import requests
    cfg = load_config(DEFAULT_CONFIG_PATH)
    print("Keymic Diagnose")
    print("=" * 50)

    py = f"{sys.version_info.major}.{sys.version_info.minor}"
    py_ok = sys.version_info >= (3, 11)
    print(f"  [{'✓' if py_ok else '✗'}] Python {py}" + (" (>= 3.11 erforderlich)" if not py_ok else ""))

    api_key = cfg["groq"].get("api_key") or os.environ.get("GROQ_API_KEY", "")
    if api_key:
        try:
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            print(f"  [{'✓' if r.status_code == 200 else '✗'}] Groq API-Key {'(gültig)' if r.status_code == 200 else '(ungültig)'}")
        except Exception as e:
            print(f"  [?] Groq API-Key (Netzwerk-Fehler: {e})")
    else:
        print("  [✗] Groq API-Key (nicht konfiguriert)")

    try:
        from keymic.platform_linux import HotkeyListener
        hotkey = cfg["general"]["hotkey"]
        with HotkeyListener(hotkey):
            print(f"  [✓] Hotkey-Device für {hotkey}")
    except Exception as e:
        print(f"  [✗] Hotkey-Device: {e}")

    if shutil.which("pw-cat"):
        print("  [✓] pw-cat gefunden")
    else:
        print("  [✗] pw-cat fehlt")

    for tool in ("ydotool", "xdotool", "wl-copy", "xclip"):
        if shutil.which(tool):
            print(f"  [✓] {tool} gefunden")

    if shutil.which("ydotoold") is None and shutil.which("xdotool") is None:
        print("  [?] ydotoold/xdotool nicht laufend — starten mit 'ydotoold &'")

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="keymic",
        description="Push-to-talk voice dictation for Linux",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    setup_parser = sub.add_parser("setup", help="interactively configure keymic")
    setup_parser.add_argument("--force", action="store_true", help="overwrite existing config")

    run_parser = sub.add_parser("run", help="start daemon in background (use --foreground for dev)")
    run_parser.add_argument("--foreground", "-f", action="store_true",
                           help="run in foreground (don't fork)")

    sub.add_parser("stop", help="stop the background daemon")
    sub.add_parser("status", help="show daemon status")
    sub.add_parser("check", help="diagnose environment")

    args = parser.parse_args(argv)
    if args.version:
        cmd_version(args)
        return 0
    handlers = {
        "setup": cmd_setup, "run": cmd_run, "stop": cmd_stop,
        "status": cmd_status, "check": cmd_check,
    }
    handler = handlers.get(args.cmd)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args) or 0


if __name__ == "__main__":
    sys.exit(main())
