# Meister Guide

Meister Guide is an AI powered Windows app written in Python that helps with any
questions you have while playing. It finds the answers on the respective game's
wiki and compiles the information to give tips, tricks and guides to improve your
gaming experience, displaying them in an overlay triggered by a programmable
hotkey (Alt + Insert). Out of the box it's online (wiki + DuckDuckGo) and works
offline once you've downloaded guides.

Try a demo out in the browser: <https://hpeen.github.io/MeisterGuide/>

OR download Meister Guide at: <https://github.com/Hpeen/MeisterGuide/releases>

## Usage Guide

### Setting it up

1. Run `MeisterGuide.exe`. It will appear in the system tray.
2. Set up a backend in the ⚙ Settings tab:
   - Claude: paste an API key from console.anthropic.com.
   - Ollama: install it, run `ollama pull llama3`, leave backend on Auto.
3. Press Alt + Insert to show or hide the overlay. NOTE: The overlay can only be on
   top in windowed or borderless windowed mode, not exclusive fullscreen.

### Asking a question

Open the Ask Meister tab and ask it questions like "How do I get a Mace?". It will
give an answer and list the pages it used. Click a source to read it in the Wiki
tab. New chat clears it, while the history dropdown reopens an old one.

### Adding another game

⚙ Settings → Add a game: enter a name, its wiki URL (ex: `https://subnautica.fandom.com`),
and the process name (ex: `Subnautica.exe`).

## Build it yourself / run from source

Run from source:

1. Install Python 3.11 or newer.
2. `python -m venv .venv && .venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `python -m meister_guide.main`

To build the `.exe`, see [BUILD.md](BUILD.md).

Run the tests with `pytest -q`.
