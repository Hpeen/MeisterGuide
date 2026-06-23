# Meister Guide 🪵

An in-game overlay that answers your questions about whatever game you're playing,
right on top of the game, so you never have to alt-tab to a wiki again.

**Try it in your browser (no install):** https://hpeen.github.io/MeisterGuide/

---

## What did I make?

You know that thing where you're playing a game, you get stuck, and you have to
tab out, open your browser, find the wiki, dig through it, and by the time you're
back you forgot what you were even doing? I hated that. So I built Meister Guide.

It's a little overlay styled like an old carpenter's journal that floats over your
game. You hit `Alt + Insert`, a panel slides up, and you just ask it stuff like
"how do I make a nether portal" or "where do I find diamonds in Subnautica." It
reads the game's wiki, finds the actual relevant pages, and writes you an answer
with the sources listed so you can check it didn't make anything up.

The best part: it isn't locked to one game. You can add **any** game that has a
wiki. You give it a name, the wiki link, and the game's .exe, and now Meister knows
that game too and switches to it automatically when you launch it. I tested it with
Minecraft (the one I built it around first) and Subnautica, but it'll work for tons
of games.

It's a Windows app written in Python with PySide6. There's also a full browser demo
so people can try it without downloading anything, which I'm really happy about.

## What was challenging?

Honestly, a lot. A few that nearly broke me:

- **Making a window stay on top of a fullscreen game.** Every tutorial skips the
  hard part. Turns out you need a frameless + always-on-top + translucent window,
  AND you have to register the hotkey at the Windows OS level (I called the raw
  Windows API directly through ctypes) so the game can't steal your keypress.

- **The AI giving dumb answers.** I asked "how do creepers work?" and it confidently
  answered using three random beta changelogs instead of the actual Creeper page.
  The AI wasn't broken, my search was. It was feeding the AI garbage because filler
  words like "how do i make a" were matching spammy patch-note pages. Fixing the
  search was way more work than adding the AI.

- **The Fandom bug that ate a whole day.** Most game wikis are on Fandom. My wiki
  fetcher worked perfectly on Minecraft's wiki and then silently stored **zero**
  articles for every Fandom game. No error, no crash, it just said "success" and
  saved nothing. Worst kind of bug. Turned out Fandom doesn't have the clean-text
  feature minecraft.wiki has, so I had to detect that and pull the text out of the
  raw HTML myself.

- **The .exe that only broke as an .exe.** I packaged everything into one
  double-click file, all my tests passed, and then it crashed the second it was
  packaged because a library's data files didn't get bundled. Lesson learned: tests
  passing from source proves nothing about the actual shipped thing.

## What am I proud of?

- It actually works and it's genuinely usable now, not a half-finished demo.
- The **any-game** thing. It started as a Minecraft tool and the whole architecture
  was secretly built to handle more than one game the whole time, so unlocking it
  felt awesome.
- The smart fallback: it checks your downloaded guides first, then the live wiki,
  then a plain web search, so it almost always finds *something*. And it works
  online out of the box with no API key needed for the web search.
- The browser demo. I wanted anyone to be able to click one link and get it, instead
  of "trust me, download this .exe." That took real effort to fake convincingly.

## How can people test it?

**Easiest (30 seconds, no install):**
Just open the demo → https://hpeen.github.io/MeisterGuide/
Click around, open the Wiki tab, switch between Minecraft and Subnautica, and try
the Ask Meister questions.

**The real app (Windows):**
1. Download `MeisterGuide.exe` from the Releases page.
2. Run it. Windows SmartScreen will warn you because it's unsigned (I can't afford a
   code-signing cert lol) → click **More info → Run anyway**. It's safe, the code is
   all right here in the repo.
3. It lives in your system tray. Press **`Alt + Insert`** to show/hide the overlay.
4. To get answers, set up an AI backend in the ⚙ Settings tab: either paste a
   **Claude API key**, or install **Ollama** (free + local) and leave it on Auto.
5. Ask it something! And to add your own game, go to ⚙ Settings → Add a game.

**Important:** run your game in **windowed** or **borderless** mode, not exclusive
fullscreen, or no overlay can sit on top of it (that's a Windows thing, not me).

Repo + source code: https://github.com/Hpeen/MeisterGuide
