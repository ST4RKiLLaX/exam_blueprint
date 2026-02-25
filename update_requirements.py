#!/usr/bin/env python3
"""Compile pinned requirements.txt from requirements.in using pip-tools."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Update pinned requirements.txt from requirements.in."
    )
    parser.add_argument(
        "--input",
        default=str(root / "requirements.in"),
        help="Path to top-level dependency file (default: requirements.in).",
    )
    parser.add_argument(
        "--output",
        default=str(root / "requirements.txt"),
        help="Path to pinned output file (default: requirements.txt).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")

    command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        str(input_path),
        "--output-file",
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "Failed to compile requirements. Ensure pip-tools is installed:\n"
            "  venv/bin/pip install pip-tools"
        ) from exc

    print(f"Pinned requirements updated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
