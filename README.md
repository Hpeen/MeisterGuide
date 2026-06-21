# Meister Guide

A rustic in-game companion overlay for PC games. Press a hotkey to bring it up
over your game and ask Meister, its built-in AI assistant, about whatever you're
stuck on. It pulls answers from the game's wiki and the web and shows you the
sources it used. It also has a wiki reader built in and works across more than one
game. Windows desktop app, written in Python with PySide6.

---

## Quick start (just want to try it)

1. Download `MeisterGuide.exe`.
2. Double-click to run it. Windows may show a blue "Windows protected your PC" box,
   since the app isn't signed. Click **More info**, then **Run anyway**.
3. The app sits in your system tray, near the clock. Nothing opens on screen at
   first.
4. Press **`Alt + Insert`** to show or hide the overlay. Double-clicking the tray
   icon works too.

Launching is the easy part. To get actual answers, do the one-time AI setup below.

---

## Step 2: Set up the AI assistant (pick one)

Meister needs an AI backend to write answers. Pick whichever fits you. You can
switch later in the **⚙ Settings** tab.

### Option A: Claude (online, easiest)
1. Get an API key at <https://console.anthropic.com>. It's paid, billed by usage.
2. In **⚙ Settings**, set the backend to **"Always online (Claude)"** (or leave it
   on **Auto**), paste your key into the **Claude API key** box, and click
   **Save**.
3. Ask away. You don't need to download any guides first; Meister fetches what it
   needs as you go.

### Option B: Ollama (free, local, works offline)
1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3`.
2. Make sure Ollama is running.
3. In **⚙ Settings**, set the backend to **"Always local (Ollama)"** (or leave it
   on **Auto**), and click **Save**.

**Auto** mode uses Claude when you've set a key and falls back to local Ollama when
you haven't, which is handy if you set up both.

---

## Using Meister

The **Ask Meister** tab is where you type questions, like "How do I tame a wolf?".
Meister finds the most relevant guide passages, streams back an answer, and lists
the pages it used. Click a source to open it in the Wiki tab. **New chat** starts
over, and the history dropdown reopens an old conversation.

The **Wiki** tab lets you search and read downloaded guide articles on their own,
without the AI.

### Where answers come from

Meister looks for knowledge in three places, in this order:

1. Your downloaded offline guides.
2. The game's wiki, fetched live for whatever you asked about.
3. A plain web search, as a last resort.

The second and third need an internet connection. The web search needs no setup
and no key; it uses DuckDuckGo. So the app is online out of the box, and it gains
an offline mode once you've downloaded some guides.

---

## Showing the overlay over your game

Run your game in windowed or borderless windowed mode, not exclusive "Fullscreen".
The overlay then sits on top while the game waits behind it. Press `Alt + Insert`
again to dismiss it and go back to the game.

Exclusive fullscreen won't work. That mode draws straight to the GPU and minimizes
the moment it loses focus, so no ordinary window can sit over it. In Minecraft
Java, fullscreen (F11) behaves that way, so play in Windowed mode instead. A
borderless-window mod gets you the full-screen look without the problem.

---

## Playing a different game

Minecraft works out of the box. To add another game, open **⚙ Settings**, find
**Add a game**, and fill in three things:

- **Name**, like `Subnautica`.
- **Wiki URL**, like `https://subnautica.fandom.com`. This is what lets Meister
  fetch guides for that game.
- **Process name(s)**, the game's executable like `Subnautica.exe`, so the app
  switches to it automatically when the game is running. You can find the exact
  name in Task Manager, under the Details tab, while the game is open.

You can also switch games by hand from the pill at the top of the overlay.

A new game has no offline guides yet, so Meister fills them in live as you ask (and
from the web search). If you'd rather have instant offline answers ready, download
guides ahead of time:

- **Seed guides from a category** (in ⚙ Settings): pick the game, type a wiki
  category like `Mobs`, and click **Seed** to pull that whole topic.
- **Update guides** (Wiki tab, Minecraft): download the entire Minecraft wiki for
  full offline coverage. It runs in the background, so you can hide the overlay and
  keep playing, and it picks up where it left off if interrupted.

To free up space later, go to **⚙ Settings**, then **Manage guides**, where you can
clear a game's guides or remove a game.

---

## Settings reference (⚙ tab)

- **AI chat backend**: Auto, Claude, or Ollama (see Step 2).
- **Claude API key**: used only by the Claude backend, stored on your machine.
- **Allow web search fallback**: on by default. Uncheck it to keep Meister offline.
- **Hotkey**: change the show/hide shortcut. The default is `Alt + Insert`.
- **Add a game / Seed guides / Manage guides**: covered above.

---

## Build it yourself / run from source

Run from source:

1. Install Python 3.11 or newer.
2. `python -m venv .venv && .venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `python -m meister_guide.main`

To build the `.exe`, see [BUILD.md](BUILD.md).

Run the tests with `pytest -q`.
