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

## AI (later phase)
Meister uses [Ollama](https://ollama.com) running locally at
`http://localhost:11434`. Install Ollama and `ollama pull llama3`.

## Tests
`pytest -q`
