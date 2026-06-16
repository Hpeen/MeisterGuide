# Meister Guide

A rustic gaming companion overlay with offline guides and a local AI assistant
("Meister"), powered by Ollama. Windows desktop, built with Python + PySide6.

## Setup
1. Install Python 3.11+.
2. `python -m venv .venv && .venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. Run: `python -m meister_guide.main`

## Hotkey
`Alt + Insert` toggles the overlay (rebindable in Settings, later phase).

## Showing the overlay over a game
Run your game in **windowed** or **borderless windowed** mode (not exclusive /
"Fullscreen"). The overlay then appears on top, and the game pauses behind it —
press `Alt + Insert` again to dismiss it and return to the game.

True exclusive fullscreen is not supported: that mode renders straight to the
GPU and minimizes itself the moment it loses focus, so any normal window (ours
included) can't sit over it. For **Minecraft Java**, fullscreen (F11) is GLFW
exclusive-style — use **Windowed** mode, or add a borderless-window mod (e.g.
Sodium/OptiFine borderless) for a seamless full-screen feel.

## Guides (offline wiki)
Open the Guides tab and click **Update guides** once to download minecraft.wiki
article text into a local database (~40 min, ~80 MB). After that, search works
fully offline. The download uses the MediaWiki API politely (identified
User-Agent, `maxlag`-guarded, resumable) and stores only plain text — no images.
It runs in the background with a progress bar and resumes if interrupted, so the
one-time wait is unattended.

## AI (later phase)
Meister uses [Ollama](https://ollama.com) running locally at
`http://localhost:11434`. Install Ollama and `ollama pull llama3`.

## Tests
`pytest -q`
