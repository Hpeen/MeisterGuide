# Meister Guide

A rustic in-game companion overlay for PC gamers. Summon it over your game with a
hotkey and ask **Meister**, an AI assistant, anything about the game — it pulls
answers from the game's wiki and the web and shows its sources. Comes with a
built-in wiki reader and works across multiple games. Windows desktop, built with
Python + PySide6.

---

## Quick start (just want to try it)

1. **Download** `MeisterGuide.exe`.
2. **Run it** by double-clicking. Windows may show a blue *"Windows protected your
   PC"* box (the app is unsigned) — click **More info → Run anyway**.
3. The app lives in your **system tray** (bottom-right, near the clock) — no window
   pops up right away.
4. Press **`Alt + Insert`** to show or hide the overlay. (You can also
   double-click the tray icon.)

That's it for launching. To actually get answers, do the one-time AI setup below.

---

## Step 2: Set up the AI assistant (pick one)

Meister needs an "AI backend" to write answers. Choose whichever suits you — you
can change it anytime in the **⚙ Settings** tab.

### Option A — Claude (online, easiest)
1. Get an API key from <https://console.anthropic.com> (paid, usage-based).
2. In **⚙ Settings**, set the backend to **"Always online (Claude)"** (or leave it
   on **Auto**), paste your key into the **Claude API key** field, and click
   **Save**.
3. Done — ask away. No guide download needed; Meister fetches what it needs live.

### Option B — Ollama (free, local, works offline)
1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3`.
2. Make sure Ollama is running.
3. In **⚙ Settings**, set the backend to **"Always local (Ollama)"** (or leave it
   on **Auto**), and click **Save**.

> **Auto** mode uses Claude when a key is set and falls back to local Ollama
> otherwise — a good default if you set up both.

---

## Using Meister

- **Ask Meister tab** — type a question (e.g. *"How do I tame a wolf?"*). Meister
  finds the most relevant guide passages, streams an answer, and lists the source
  pages — click a source to open it in the Wiki tab. Use **New chat** to start
  fresh or the history dropdown to reopen a past conversation.
- **Wiki tab** — search and read downloaded guide articles directly (no AI needed).

### Where answers come from
Meister looks for knowledge in this order, automatically:
1. **Your offline guides** (downloaded articles), then
2. the **game's wiki**, fetched live for the topic you asked about, then
3. a **free web search** as a last resort.

Steps 2–3 need an internet connection. The free web search works with **no setup
and no key** (it uses DuckDuckGo). The app is online-first out of the box, with an
offline mode once you've downloaded guides.

---

## Showing the overlay over your game

Run your game in **windowed** or **borderless windowed** mode (not exclusive /
"Fullscreen"). The overlay then appears on top and the game sits behind it. Press
`Alt + Insert` again to dismiss it and return to the game.

True exclusive fullscreen isn't supported — that mode renders straight to the GPU
and minimizes the instant it loses focus, so no normal window can sit over it. For
**Minecraft Java**, fullscreen (F11) is exclusive-style, so use **Windowed** mode
(or a borderless-window mod) for a seamless full-screen feel.

---

## Playing a different game

Minecraft is set up out of the box. To add another game, open **⚙ Settings →
Add a game** and fill in:

- **Name** — e.g. `Subnautica`.
- **Wiki URL** — the game's wiki, e.g. `https://subnautica.fandom.com`. This is
  what lets Meister fetch guides for it.
- **Process name(s)** — the game's executable, e.g. `Subnautica.exe`, so the app
  auto-switches when the game is running. Find it in **Task Manager → Details**
  while the game is open. (You can also switch games manually from the pill at the
  top of the overlay.)

A new game starts with no offline guides — Meister fills them in live as you ask
(and via the web search). For instant, offline answers, download guides up front:

- **Seed guides from a category** (⚙ Settings) — pick the game, type a wiki
  category (e.g. `Mobs`), and click **Seed** to pull that whole topic.
- **Update guides** (Wiki tab, Minecraft) — download the full Minecraft wiki for
  complete offline coverage. It runs in the background (you can hide the overlay
  and keep playing) and resumes if interrupted.

You can free up space anytime in **⚙ Settings → Manage guides** (clear a game's
guides, or remove a game).

---

## Settings reference (⚙ tab)

- **AI chat backend** — Auto / Claude / Ollama (see Step 2).
- **Claude API key** — only used by the Claude backend; stored locally.
- **Allow web search fallback** — on by default; uncheck to keep Meister offline.
- **Hotkey** — rebind the show/hide shortcut (default `Alt + Insert`).
- **Add a game / Seed guides / Manage guides** — see above.

---

## Build it yourself / run from source

**Run from source:**
1. Install Python 3.11+.
2. `python -m venv .venv && .venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `python -m meister_guide.main`

**Build the `.exe`:** see [BUILD.md](BUILD.md).

**Tests:** `pytest -q`
