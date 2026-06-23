# Meister Guide

Meister Guide is an AI powered Windows app written in Python that helps with any
questions you have while playing. It finds the answers on the respective game's
wiki and compiles the information to give tips, tricks and guides to improve your
gaming experience, displaying them in an overlay triggered by a programmable hotkey
(Alt + Insert). Out of the box it's online (wiki + DuckDuckGo) and works offline
once you've downloaded guides.

![Meister Guide overlay sitting over a game, showing the wiki reader with indexed guides](assets/hero.png)

## Try it

**Demo in your browser :** <https://hpeen.github.io/MeisterGuide/>

**Download for Windows:** <https://github.com/Hpeen/MeisterGuide/releases>

The browser demo is just a preview, it doesn't have AI capabilities.

## Features

- Floats over your game with a global hotkey (Alt + Insert), even when the game has
  grabbed your keyboard.
- Answers come from the game's wiki with a web fallback, and every claim links a source.
- Three places to look: your offline guides, the live wiki and then a web
  search.
- Online out of the box (wiki + DuckDuckGo, no account or key for web search) and
  works offline once you've downloaded guides.
- Handles more than one game, with a built-in wiki reader for browsing guides on
  their own.
- Pick your backend: Claude (online) or Ollama (local and free).

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

## How it works

Ask Meister something and it checks  the guides you've already downloaded.
If those come up short, it grabs the game's wiki live for exactly what you asked.
IF even that draws a blank, there's a plain web search waiting at the bottom. 
You almost never walk away with nothing!

Getting the text out of those wikis was the annoying part. minecraft.wiki is polite
about it and hands over clean plain text. Most Fandom wikis are not so polite... They
don't have that extension installed, so the same request comes back empty.
Meister pokes each wiki once to see what it's dealing with, remembers the answer,
and never asks twice. No plain-text API? No problem. It grabs the full rendered page
instead and lets trafilatura dig the real article out of the HTML. Either way you
land in the same spot, which is why adding a new Fandom game just works.

## Build it yourself / run from source

Python 3.11 or newer, and a backend to answer questions: either a Claude API key
(entered in the app, stored on your machine) or a running Ollama install. See
[BUILD.md](BUILD.md) to run from source or build the `.exe`.

## Credits

Built with [PySide6](https://doc.qt.io/qtforpython/) (Qt for Python) for the
overlay, [trafilatura](https://trafilatura.readthedocs.io/) for extracting article
text from wiki pages, [Ollama](https://ollama.com) for local models, and
[Claude](https://www.anthropic.com) for the online backend. Web search uses
DuckDuckGo, and guide content comes from the community wikis on minecraft.wiki and
Fandom.
