import argparse
import os
import subprocess
from pathlib import Path
import openai

# === CONFIG ===
client = openai.OpenAI()
CLAUDE_CLI_CMD = "claude"
MAX_TOKENS_GPT5 = 128000
APPROX_CHARS_PER_TOKEN = 4
MAX_CHARS = MAX_TOKENS_GPT5 * APPROX_CHARS_PER_TOKEN  # ~500k characters

INCLUDE_EXTENSIONS = {
    '.py', '.js', '.ts', '.html', '.css', '.json', '.md', '.txt',
    '.c', '.cpp', '.java'
}

DEFAULT_OUTPUT_FILE = "gpt_analysis_output.md"
GPTIGNORE_FILE = ".gptignore"

# === GPT FUNCTION WITH STREAMING & FILE OUTPUT ===
def run_gpt_stream(prompt, model="gpt-4o", output_file=DEFAULT_OUTPUT_FILE):
    try:
        print("\n🧠 GPT is analyzing your codebase...\n")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a senior software engineer analyzing a Python web app's UI/UX. Be thorough, professional, and offer actionable insight."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            stream=True
        )

        with open(output_file, "w", encoding="utf-8") as f:
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    print(content, end="", flush=True)
                    f.write(content)

        print(f"\n\n✅ GPT response complete. Saved to `{output_file}`.")
        return output_file

    except Exception as e:
        return f"GPT Error: {e}"

# === CLAUDE (CLI) ===
def run_claude(prompt):
    try:
        result = subprocess.run([CLAUDE_CLI_CMD, prompt], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Claude CLI Error: {e}"

# === IGNORE FILTER ===
def load_gptignore():
    patterns = []
    if os.path.exists(GPTIGNORE_FILE):
        with open(GPTIGNORE_FILE, "r") as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            patterns = lines
    return patterns

def should_ignore(path: Path, ignore_patterns):
    for pattern in ignore_patterns:
        if path.match(pattern) or any(part in pattern for part in str(path).split(os.sep)):
            return True
    return False

# === FILE COLLECTION & FILTERING ===
def collect_files(file_paths, dir_path, ignore_patterns):
    all_files = []

    if file_paths:
        for path in file_paths:
            p = Path(path)
            if p.is_file() and not should_ignore(p, ignore_patterns):
                all_files.append(p)

    if dir_path:
        dir_root = Path(dir_path)
        if dir_root.is_dir():
            for f in dir_root.rglob("*"):
                if f.suffix.lower() in INCLUDE_EXTENSIONS and f.is_file() and not should_ignore(f, ignore_patterns):
                    all_files.append(f)

    return all_files

# === LOAD FILES (WITH TRUNCATION) ===
def load_code_from_files(files):
    content = ""
    total_chars = 0

    sorted_files = sorted(files, key=lambda f: f.stat().st_size)

    for file in sorted_files:
        try:
            text = file.read_text(encoding='utf-8')
            file_block = f"\n\n# File: {file}\n{text}\n"
            if total_chars + len(file_block) > MAX_CHARS:
                print(f"⚠️  Truncating at: {file} (token limit reached)")
                break
            content += file_block
            total_chars += len(file_block)
        except Exception as e:
            content += f"\n\n# File: {file}\n# ERROR: {e}\n"

    return content

# === MAIN ===
def main():
    parser = argparse.ArgumentParser(description="Analyze codebase with GPT or Claude.")
    parser.add_argument("--file", nargs='*', help="One or more file paths to analyze")
    parser.add_argument("--dir", help="Directory to recursively analyze")
    parser.add_argument("--prompt", help="Optional additional instruction")
    parser.add_argument("--model", choices=["claude", "gpt"], default="gpt", help="Model to use (GPT or Claude)")
    parser.add_argument("--output", help="Output Markdown file", default=DEFAULT_OUTPUT_FILE)

    args = parser.parse_args()
    ignore_patterns = load_gptignore()

    files = collect_files(args.file, args.dir, ignore_patterns)
    if not files:
        print("❌ No valid files found.")
        return

    code_block = load_code_from_files(files)

    base_prompt = (
        f"Please analyze the following codebase consisting of {len(files)} files from a UI/UX perspective. "
        f"Identify layout patterns, design logic, templating structure (e.g., in 'templates/' or 'static/'), "
        f"user interaction flow, and how intuitive the experience is for end users.\n"
        f"{code_block}"
    )

    if args.prompt:
        base_prompt += f"\n\nAdditional instruction:\n{args.prompt}"

    if args.model == "claude":
        result = run_claude(base_prompt)
        print(f"\n🧠 Response from CLAUDE:\n")
        print(result)
    else:
        _ = run_gpt_stream(base_prompt, model="gpt-4o", output_file=args.output)

if __name__ == "__main__":
    main()
