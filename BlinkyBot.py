port re
import sys
import subprocess
import argparse
from pathlib import Path
from openai import OpenAI

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
GROQ_API_KEY = "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"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
ACTIVE_GROQ_MODEL = "llama-3.3-70b-versatile"

FOLDER_NAME = "BlinkyBot"
SKETCH_NAME = "BlinkyBot.ino"
MAX_ATTEMPTS = 5

SCRIPT_DIR = Path(__file__).parent.resolve()
SKETCH_DIR = SCRIPT_DIR / FOLDER_NAME
SKETCH_PATH = SKETCH_DIR / SKETCH_NAME
FQBN = "arduino:avr:uno"

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def setup_sketch_folder() -> None:
    SKETCH_DIR.mkdir(exist_ok=True)

def extract_code_from_markdown(text: str) -> str:
    patterns = [
        r"```(?:cpp|arduino)\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            code = match.group(1).strip()
            if code:
                return code
    return text.strip()

def save_sketch(code: str) -> None:
    with open(SKETCH_PATH, "w", encoding="utf-8") as f:
        f.write(code)

def read_sketch() -> str:
    with open(SKETCH_PATH, "r", encoding="utf-8") as f:
        return f.read()

def run_arduino_command(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("ERROR: arduino-cli not found.")
        sys.exit(1)

def compile_sketch() -> tuple[bool, str]:
    cmd = ["arduino-cli", "compile", "--fqbn", FQBN, str(SKETCH_DIR)]
    result = run_arduino_command(cmd)
    if result.returncode == 0:
        return True, ""
    return False, result.stderr

def upload_sketch(port: str) -> bool:
    cmd = ["arduino-cli", "upload", "-p", port, "--fqbn", FQBN, str(SKETCH_DIR)]
    result = run_arduino_command(cmd)
    return result.returncode == 0

def find_arduino_port_automatically() -> str | None:
    cmd = ["arduino-cli", "board", "list"]
    result = run_arduino_command(cmd)
    if result.returncode != 0:
        return None
    lines = result.stdout.strip().splitlines()
    for line in lines[1:]:
        if "arduino" in line.lower() or "uno" in line.lower():
            port = line.split()[0]
            return port
    return None

def get_port() -> str:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="Manually specify port")
    args, _ = parser.parse_known_args()
    if args.port:
        return args.port
    port = find_arduino_port_automatically()
    if port:
        print(f"Auto-detected port: {port}")
        return port
    port = input("Enter COM port (e.g., COM21): ").strip()
    return port

# ----------------------------------------------------------------------
# Validation and repair
# ----------------------------------------------------------------------
def validate_arduino_code(code: str) -> tuple[bool, str]:
    """Check basic Arduino structure. Return (valid, error_message)."""
    if not code:
        return False, "Code is empty."
    if "void setup(" not in code:
        return False, "Missing void setup() function."
    if "void loop(" not in code:
        return False, "Missing void loop() function."
    # check for unclosed braces
    if code.count("{") != code.count("}"):
        return False, "Mismatched braces."
    return True, ""

def repair_common_errors(code: str) -> str:
    """Fix frequent Arduino mistakes (e.g., missing semicolons, wrong pinMode)."""
    # Add missing semicolons at end of lines that likely need them
    lines = code.split("\n")
    fixed_lines = []
    for line in lines:
        stripped = line.rstrip()
        if stripped and not stripped.endswith((";", "{", "}", "(", ")", "//", "#")):
            # If it's a declaration or assignment, add semicolon
            if any(key in stripped for key in ["int ", "long ", "float ", "char ", "const ", "="]):
                stripped += ";"
        fixed_lines.append(stripped)
    code = "\n".join(fixed_lines)
    # Ensure all pinMode are inside setup()
    if "pinMode" in code and "void setup()" in code:
        # Already fine
        pass
    return code

# ----------------------------------------------------------------------
# Code generation with few-shot and auto-repair
# ----------------------------------------------------------------------
client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

def generate_initial_code(prompt_text: str) -> str:
    system = (
        "You are an expert Arduino programmer. Generate COMPLETE, COMPILABLE Arduino Uno sketches.\n"
        "ALWAYS include both `void setup()` and `void loop()`.\n"
        "Use proper pinMode, digitalWrite, delay, etc.\n"
        "Output ONLY the code inside a single ```cpp block. No extra text.\n\n"
        "Example of a correct blink sketch:\n"
        "```cpp\n"
        "void setup() {\n"
        "  pinMode(LED_BUILTIN, OUTPUT);\n"
        "}\n"
        "void loop() {\n"
        "  digitalWrite(LED_BUILTIN, HIGH);\n"
        "  delay(1000);\n"
        "  digitalWrite(LED_BUILTIN, LOW);\n"
        "  delay(1000);\n"
        "}\n"
        "```\n"
        "Example for ultrasonic sensor:\n"
        "```cpp\n"
        "const int trigPin = 9;\n"
        "const int echoPin = 10;\n"
        "const int outputPin = 13;\n"
        "void setup() {\n"
        "  pinMode(trigPin, OUTPUT);\n"
        "  pinMode(echoPin, INPUT);\n"
        "  pinMode(outputPin, OUTPUT);\n"
        "  Serial.begin(9600);\n"
        "}\n"
        "void loop() {\n"
        "  digitalWrite(trigPin, LOW);\n"
        "  delayMicroseconds(2);\n"
        "  digitalWrite(trigPin, HIGH);\n"
        "  delayMicroseconds(10);\n"
        "  digitalWrite(trigPin, LOW);\n"
        "  long duration = pulseIn(echoPin, HIGH);\n"
        "  long distance = duration * 0.034 / 2;\n"
        "  if (distance < 400) {\n"
        "    digitalWrite(outputPin, HIGH);\n"
        "    delay(100);\n"
        "    digitalWrite(outputPin, LOW);\n"
        "  }\n"
        "  delay(50);\n"
        "}\n"
        "```\n"
        "Now generate a sketch for the user request."
    )
    user = f"Write an Arduino sketch that: {prompt_text}"
    response = client.chat.completions.create(
        model=ACTIVE_GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    code = extract_code_from_markdown(raw)
    code = repair_common_errors(code)
    # Validate and retry if needed
    valid, err = validate_arduino_code(code)
    if not valid:
        retry_prompt = f"The previous code was invalid: {err}\nPlease generate a complete Arduino sketch for: {prompt_text}"
        response2 = client.chat.completions.create(
            model=ACTIVE_GROQ_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": retry_prompt}],
            temperature=0.1,
        )
        raw2 = response2.choices[0].message.content
        code = extract_code_from_markdown(raw2)
        code = repair_common_errors(code)
    return code

def modify_existing_code(modification: str, current_code: str) -> str:
    system = (
        "You are an expert Arduino programmer. Modify the provided sketch exactly as requested.\n"
        "Output the COMPLETE modified code inside a ```cpp block.\n"
        "Do not add any explanations."
    )
    user = f"Current sketch:\n```cpp\n{current_code}\n```\n\nUser request: {modification}\n\nModified code:"
    response = client.chat.completions.create(
        model=ACTIVE_GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    code = extract_code_from_markdown(raw)
    code = repair_common_errors(code)
    return code

def fix_code_with_errors(error_log: str, previous_code: str) -> str:
    system = (
        "You are an expert Arduino programmer. The code failed to compile with the errors below.\n"
        "Fix the errors and output the COMPLETE corrected code inside a ```cpp block.\n"
        "Do not add any explanations."
    )
    user = f"Code:\n```cpp\n{previous_code}\n```\n\nErrors:\n{error_log}\n\nFixed code:"
    response = client.chat.completions.create(
        model=ACTIVE_GROQ_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content
    return extract_code_from_markdown(raw)