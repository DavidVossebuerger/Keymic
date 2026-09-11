# Keymic

Push-to-talk voice dictation for Linux. Hold a hotkey, speak, release — the
transcribed text appears in the focused window.

## Features

- **Push-to-talk** with any keyboard key (default: Right Ctrl)
- **Local-first** — audio is captured, sent to Groq Whisper, then injected. No server runs on your machine.
- **PipeWire / PulseAudio / X11 / Wayland** support out of the box
- **Optional AI cleanup** via Groq LLM (handles self-corrections like "15, sorry, 17")
- **Configurable hotkey, language, vocabulary**
- **Heuristic cleanup** for fast, offline-friendly post-processing (no API call needed for filler-word removal)

## Requirements

- Linux
- Python 3.11 or newer
- A Groq API key (free tier available at https://console.groq.com/keys)
- A working microphone
- `pipewire` (or `pulseaudio`), plus one of: `ydotool` (Wayland), `xdotool` (X11), or `wl-clipboard`/`xclip`

## Quickstart

```bash
git clone https://github.com/DavidVossebuerger/Speech-Public.git
cd Speech-Public
./setup.sh
```

The setup script will:
1. Install system packages (Arch or Debian-based)
2. Add your user to the `input` and `audio` groups
3. Install Python dependencies
4. Start `ydotoold` if Wayland is detected
5. Run the interactive configuration

After setup, run the daemon:

```bash
python -m keymic run
```

Hold **Right Ctrl**, speak, release. The text appears wherever your cursor is.

## Configuration

The config file lives at `~/.config/keymic/config.toml` (XDG-compliant).

```toml
[general]
hotkey = "KEY_RIGHTCTRL"   # any KEY_* from Linux input event codes
language = "de"             # "auto", "de", "en"

[groq]
model = "whisper-large-v3"
prompt = "Eigennamen: Foo, Bar"   # helps Whisper recognize custom words
vocab = ["Foo", "Bar"]

[postprocess]
ai_postprocess = false     # disable AI cleanup by default
```

After editing, restart the daemon.

### Change the hotkey

Run the setup again with `--force`:

```bash
python -m keymic setup --force
```

Or edit `~/.config/keymic/config.toml` directly. Use any `KEY_*` constant from
the [Linux input event codes](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/include/uapi/linux/input-event-codes.h).

### Enable AI cleanup

AI cleanup is off by default because the LLM can rewrite longer transcriptions.
If you want it:

```toml
[postprocess]
ai_postprocess = true
```

The LLM will remove fillers, fix grammar, and resolve mid-sentence
self-corrections like "Hallo, ich bin um 15, nee sorry, 17 Uhr da" → "Hallo,
ich bin um 17 Uhr da."

## Troubleshooting

**"No keyboard device found"**
Your user is not in the `input` group. Run `sudo usermod -aG input $USER` and
log out and back in.

**"No injection tool found"**
Install `ydotool` (Wayland) or `xdotool` (X11). On Wayland, also start the
daemon: `ydotoold &`

**Microphone not detected**
Check PipeWire/PulseAudio: `pactl list sources short`. Update `[general] audio_device`
in the config to the exact source name, or leave as `"auto"`.

**API key invalid**
Get a fresh key at https://console.groq.com/keys. The setup script validates it.

## Commands

| Command | Description |
|---|---|
| `python -m keymic setup` | Interactive configuration (asks install mode + API key + hotkey) |
| `python -m keymic run` | Start daemon in background (returns immediately) |
| `python -m keymic run --foreground` | Start daemon in foreground (Ctrl+C to stop) |
| `python -m keymic stop` | Stop the background daemon |
| `python -m keymic status` | Show daemon status, PID, log path |
| `python -m keymic check` | Diagnose environment |
| `python -m keymic --version` | Print version |

After `keymic setup` with install mode 1 (User-Install) or 2 (System-Install),
the `keymic` command is also available directly:

| Command | Description |
|---|---|
| `keymic run` | Start daemon (after user-install) |
| `keymic status` | Show status |
| `keymic stop` | Stop daemon |

## Install modes (during setup)

The setup flow asks which install mode you want:

1. **User-Install (recommended)**: `pip install --user -e .`
   - `keymic` is available in `~/.local/bin/keymic`
   - `python -m keymic` works from anywhere
   - Add to PATH if needed: `echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc`

2. **System-Install**: `sudo pip install -e .`
   - `keymic` is available system-wide
   - Requires sudo

3. **Skip**: only write config, no installation
   - Use only from the cloned directory or a project venv
   - Best for sandboxed testing or Docker containers

## Running as a systemd user service

```bash
mkdir -p ~/.config/systemd/user
cp systemd/keymic.service ~/.config/systemd/user/
# Set your API key in ~/.config/keymic/keymic.env:
#   echo "GROQ_API_KEY=gsk_..." > ~/.config/keymic/keymic.env
# Then add EnvironmentFile= to the [Service] section.
systemctl --user daemon-reload
systemctl --user enable --now keymic.service
```

## AI Disclosure

This project's code was developed with significant AI assistance
([Claude Code](https://claude.com/claude-code) by Anthropic). The
human author drove the project — requirements, design decisions,
architecture choices, naming, target audience, testing, and all bug
fixes. The AI implemented the code based on those decisions, wrote
tests, and iterated on the human's feedback.

The architectural pattern (EVIOCGRAB + UInput replayer for non-hotkey
keys) is borrowed from the original push-to-talk daemon the author
maintained privately before this rewrite.

## License

MIT

## Acknowledgements

Built on top of:
- [Groq](https://groq.com) for Whisper inference
- [evdev](https://python-evdev.readthedocs.io/) for keyboard event capture
- [pw-cat](https://pipewire.org/) for audio recording
- [ydotool](https://github.com/ReimuNotMoe/ydotool) / [xdotool](https://www.xdotool.org/) for text injection
