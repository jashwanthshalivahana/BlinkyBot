# BlinkyBot

**Generative AI for Seamless IoT Prototyping**

Describe an IoT project in plain English — BlinkyBot writes the Arduino code, detects your board, and flashes it automatically.

## Demo

[Insert video link or GIF]

## How It Works

1. User enters a natural language prompt: *"blink the built-in LED every half second"*
2. LLM (OpenAI API) generates complete Arduino `.ino` sketch
3. PySerial auto-detects connected Arduino COM port
4. Arduino CLI compiles and flashes the board

## Tech Stack

- Python
- OpenAI API
- PySerial
- Arduino CLI

## Key Achievement

**Reduces time-to-first-blink from ~30 minutes to under 60 seconds**

## Installation

```bash
git clone https://github.com/yourusername/BlinkyBot.git
cd BlinkyBot
pip install -r requirements.txt
python blinkybot.py
