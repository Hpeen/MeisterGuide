# Meister Guide v1.0.0

A rustic in-game companion overlay for PC games. Press a hotkey to bring it up over
your game and ask Meister, its built-in AI assistant, about whatever you're stuck on.
It reads the game's wiki and the web, writes you an answer, and shows the sources it
used. Works for any game with a wiki, not just Minecraft.

**Want to try it without downloading?** Open the live browser demo:
https://hpeen.github.io/MeisterGuide/

## Download

Grab **`MeisterGuide.exe`** below. It's a single file, Windows only.

It's unsigned, so Windows SmartScreen will show a "Windows protected your PC" box.
Click **More info → Run anyway**. The full source is in this repo if you want to check
it or build it yourself.

## Getting started

1. Run `MeisterGuide.exe`. It lives in your system tray, near the clock.
2. Press **`Alt + Insert`** to show or hide the overlay (double-clicking the tray icon
   works too).
3. To get answers, set up an AI backend in the **⚙ Settings** tab, pick one:
   - **Claude** — paste an API key from <https://console.anthropic.com> (paid, billed
     by usage). Easiest, no downloads.
   - **Ollama** — free and fully local. Install [Ollama](https://ollama.com),
     run `ollama pull llama3`, and leave the backend on Auto.
4. Ask away in the **Ask Meister** tab.

## Adding your own game

Minecraft works out of the box. To add another, open **⚙ Settings → Add a game** and
give it a name, the wiki URL (e.g. `https://subnautica.fandom.com`), and the game's
process name (e.g. `Subnautica.exe`). Meister fetches guides for it live as you ask.

## Good to know

- **Run your game in windowed or borderless mode**, not exclusive fullscreen. No
  overlay can sit on top of exclusive fullscreen (that's a Windows limitation).
- Web search works with **no API key** out of the box (it uses DuckDuckGo), so the app
  is useful online immediately and earns an offline mode once you download guides.
- Your data and API key stay on your machine.

## Highlights this release

- Add and play **any game** with a wiki, not just Minecraft.
- Live wiki fetch-on-demand, so a new game answers questions right away with no big
  download required.
- Three-tier answers: your offline guides → the live wiki → a plain web search.
- Built-in wiki reader, multiple AI backends (Claude / Ollama / Auto), and a
  carpenter's-journal overlay you can dock to either screen edge.

Full usage docs: see the [README](https://github.com/Hpeen/MeisterGuide#readme).
