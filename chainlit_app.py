import chainlit as cl
import asyncio  # <--- THIS MUST BE LINE 2
from openai import OpenAI
from BlinkyBot import (
    generate_initial_code,
    modify_existing_code,
    fix_code_with_errors,
    compile_sketch,
    upload_sketch,
    get_port,
    save_sketch,
    extract_code_from_markdown,
    validate_arduino_code,
)

# ----------------------------------------------------------------------
# Groq client setup (for casual chat)
# ----------------------------------------------------------------------
GROQ_API_KEY = "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"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"
client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

# ----------------------------------------------------------------------
# Conversation memory
# ----------------------------------------------------------------------
def get_conversation_history() -> list:
    return cl.user_session.get("conversation_history", [])

def add_to_history(role: str, content: str):
    history = get_conversation_history()
    history.append({"role": role, "content": content})
    if len(history) > 20:
        history = history[-20:]
    cl.user_session.set("conversation_history", history)

# ----------------------------------------------------------------------
# Conversational AI
# ----------------------------------------------------------------------
async def chat_with_ai(prompt: str, system_message: str = "You are BlinkyBot, a helpful Arduino assistant.") -> str:
    messages = [{"role": "system", "content": system_message}]
    messages.extend(get_conversation_history())
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.7,
    )
    reply = response.choices[0].message.content
    add_to_history("user", prompt)
    add_to_history("assistant", reply)
    return reply

# ----------------------------------------------------------------------
# Code generation with memory and retro-validation
# ----------------------------------------------------------------------
async def generate_code_with_memory(user_input: str, current_code: str, is_modification: bool) -> str:
    """Generate or modify code, with built-in validation and retry."""
    if is_modification and current_code:
        code = modify_existing_code(user_input, current_code)
    else:
        code = generate_initial_code(user_input)
    valid, err = validate_arduino_code(code)
    if not valid:
        if is_modification and current_code:
            code = modify_existing_code(f"{user_input}\n\nThe previous output was invalid: {err}", current_code)
        else:
            code = generate_initial_code(f"{user_input}\n\nThe previous output was invalid: {err}")
    return code

# ----------------------------------------------------------------------
# Compile & upload with auto-fix loop
# ----------------------------------------------------------------------
async def compile_and_upload(code: str, port: str) -> tuple[bool, str]:
    save_sketch(code)
    current_code = code
    for attempt in range(1, 6):
        ok, err = compile_sketch()
        if ok:
            if upload_sketch(port):
                return True, "✅ Upload successful! Sketch is running."
            else:
                return False, "❌ Upload failed. Check port and cable."
        else:
            if attempt == 5:
                return False, f"❌ Compilation failed after 5 attempts.\n```\n{err}\n```"
            try:
                fixed = fix_code_with_errors(err, current_code)
                save_sketch(fixed)
                current_code = fixed
            except Exception as e:
                return False, f"❌ AI fix failed: {e}"
    return False, "Unexpected error."

# ----------------------------------------------------------------------
# Mode UI
# ----------------------------------------------------------------------
async def send_mode_message():
    mode = cl.user_session.get("auto_upload_mode", False)
    mode_text = "⚡ Auto Mode (uploads directly)" if mode else "🔘 Ask Mode (asks before upload)"
    actions = [
        cl.Action(name="set_ask_mode", payload={"mode": "ask"}, label="🔘 Ask Mode", description="Ask before upload"),
        cl.Action(name="set_auto_mode", payload={"mode": "auto"}, label="⚡ Auto Mode", description="Upload directly")
    ]
    await cl.Message(content=f"📌 Current mode: {mode_text}\n\nUse buttons or type `!ask` / `!auto`.", actions=actions).send()

@cl.action_callback("set_ask_mode")
async def set_ask_mode(action: cl.Action):
    cl.user_session.set("auto_upload_mode", False)
    await cl.Message(content="✅ Switched to Ask Mode.").send()
    await send_mode_message()

@cl.action_callback("set_auto_mode")
async def set_auto_mode(action: cl.Action):
    cl.user_session.set("auto_upload_mode", True)
    await cl.Message(content="✅ Switched to Auto Mode.").send()
    await send_mode_message()

# ----------------------------------------------------------------------
# Chainlit entry points
# ----------------------------------------------------------------------
import asyncio # Ensure this is at the top of your chainlit_app.py


@cl.on_chat_start
async def start():
    port = get_port()
    cl.user_session.set("port", port)
    # ... other session setup ...

    # The logic for the welcome screen
    welcome_msg = cl.Message(content=f"BlinkyBot connected on {port}")
    await welcome_msg.send()

    await asyncio.sleep(2)  # <--- Check this line for typos!
    await welcome_msg.remove()

    await send_mode_message()

@cl.on_message
async def main(message: cl.Message):
    user_input = message.content.strip()
    if not user_input:
        return

    # mode commands
    if user_input.lower() in ["!ask", "ask mode"]:
        cl.user_session.set("auto_upload_mode", False)
        await cl.Message(content="✅ Ask Mode enabled.").send()
        await send_mode_message()
        return
    if user_input.lower() in ["!auto", "auto mode"]:
        cl.user_session.set("auto_upload_mode", True)
        await cl.Message(content="✅ Auto Mode enabled.").send()
        await send_mode_message()
        return

    port = cl.user_session.get("port")
    current_code = cl.user_session.get("current_code", "")
    awaiting = cl.user_session.get("awaiting_confirmation", False)
    auto_mode = cl.user_session.get("auto_upload_mode", False)

    # ---- Pending confirmation ----
    if awaiting:
        yes_words = ["yes", "upload", "go ahead", "please upload", "ok", "proceed"]
        if any(word in user_input.lower() for word in yes_words):
            pending = cl.user_session.get("pending_code")
            if pending:
                msg = cl.Message(content="⏳ Compiling and uploading...")
                await msg.send()
                success, result = await compile_and_upload(pending, port)
                if success:
                    cl.user_session.set("current_code", pending)
                    cl.user_session.set("awaiting_confirmation", False)
                    cl.user_session.set("pending_code", None)
                    await cl.Message(content=result).send()
                else:
                    await cl.Message(content=result).send()
                    cl.user_session.set("awaiting_confirmation", False)
            else:
                await cl.Message(content="No pending code.").send()
                cl.user_session.set("awaiting_confirmation", False)
        else:
            # Modify pending code instead
            cl.user_session.set("awaiting_confirmation", False)
            pending = cl.user_session.get("pending_code")
            if pending:
                new_code = await generate_code_with_memory(user_input, pending, is_modification=True)
                cl.user_session.set("pending_code", new_code)
                cl.user_session.set("awaiting_confirmation", True)
                await cl.Message(content=f"```cpp\n{new_code}\n```\n\nShould I compile and upload this?").send()
            else:
                await cl.Message(content="No pending code to modify.").send()
        return

    # ---- Show code ----
    if user_input.lower() in ["show code", "show sketch"]:
        if current_code:
            await cl.Message(content=f"```cpp\n{current_code}\n```").send()
        else:
            await cl.Message(content="No sketch yet.").send()
        return

    # ---- Detect if sketch request ----
    sketch_keywords = ["write", "generate", "create", "make", "code for", "sketch", "program", "blink", "led", "sensor", "motor", "servo"]
    is_sketch_request = any(kw in user_input.lower() for kw in sketch_keywords) and not any(
        q in user_input.lower() for q in ["what is", "how to", "why", "explain"]
    )

    if not is_sketch_request:
        thinking = cl.Message(content="🤔 Let me think...")
        await thinking.send()
        reply = await chat_with_ai(user_input, "You are BlinkyBot, an expert Arduino assistant. Answer helpfully.")
        thinking.content = reply
        await thinking.update()
        return

    # ---- Generate or modify code ----
    is_modification = (current_code != "") and any(kw in user_input.lower() for kw in ["change", "modify", "update", "make it", "instead"])
    msg = cl.Message(content="🤖 Generating code...")
    await msg.send()

    try:
        new_code = await generate_code_with_memory(user_input, current_code, is_modification)
        valid, err_msg = validate_arduino_code(new_code)
        if not valid:
            msg.content = f"⚠️ Auto-validation failed: {err_msg}. Retrying..."
            await msg.update()
            new_code = await generate_code_with_memory(f"{user_input} (fix: {err_msg})", current_code, is_modification)
    except Exception as e:
        msg.content = f"❌ Error: {e}"
        await msg.update()
        return

    msg.content = "✅ Code generated successfully."
    await msg.update()
    await cl.Message(content=f"```cpp\n{new_code}\n```").send()

    # ---- Decide upload ----
    force_auto = any(kw in user_input.lower() for kw in ["upload directly", "auto upload"])
    if auto_mode or force_auto:
        await cl.Message(content="🚀 Uploading directly...").send()
        success, result = await compile_and_upload(new_code, port)
        if success:
            cl.user_session.set("current_code", new_code)
            await cl.Message(content=result).send()
        else:
            await cl.Message(content=result).send()
    else:
        cl.user_session.set("pending_code", new_code)
        cl.user_session.set("awaiting_confirmation", True)
        await cl.Message(content="❓ Should I compile and upload this sketch? (Reply 'yes' or 'upload')").send()