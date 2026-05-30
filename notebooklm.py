#!/usr/bin/env python3
import os
import sys
import argparse
from pathlib import Path
import anthropic


def load_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            print(f"Warning: pypdf not installed, skipping {path.name}", file=sys.stderr)
            return ""
    return path.read_text(encoding="utf-8", errors="replace")


def build_system_prompt(docs: dict) -> str:
    parts = [
        "Answer questions based solely on the provided documents. "
        "If the answer is not in the documents, say so clearly.\n"
    ]
    for name, content in docs.items():
        parts.append(f'<document name="{name}">\n{content}\n</document>')
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="NotebookLM-py: document Q&A powered by Claude"
    )
    parser.add_argument("documents", nargs="+", help="Document files to load")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    docs = {}
    for doc_str in args.documents:
        path = Path(doc_str)
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        content = load_document(path)
        if content.strip():
            docs[path.name] = content
            print(f"Loaded: {path.name} ({len(content):,} chars)")
        else:
            print(f"Warning: {path.name} is empty or unreadable", file=sys.stderr)

    if not docs:
        print("Error: No documents loaded", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt(docs)
    history = []

    print(f"\n{len(docs)} document(s) loaded. Ask questions or type 'exit' to quit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        history.append({"role": "user", "content": question})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=history,
        )

        answer = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        history.append({"role": "assistant", "content": answer})
        print(f"\nAssistant: {answer}\n")


if __name__ == "__main__":
    main()
