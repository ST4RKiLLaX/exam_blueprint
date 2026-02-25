#!/usr/bin/env python3
"""Generate a local CycloneDX JSON SBOM from requirements.txt."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    root_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate CycloneDX SBOM from requirements.txt."
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=str(root_dir / "sbom.cdx.json"),
        help="Output JSON path (default: ./sbom.cdx.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root_dir = Path(__file__).resolve().parent
    requirements_file = root_dir / "requirements.txt"
    output_path = Path(args.output).resolve()

    local_tool = Path(sys.executable).parent / "cyclonedx-py"
    cyclonedx_tool = str(local_tool) if local_tool.exists() else shutil.which("cyclonedx-py")
    if not cyclonedx_tool:
        raise SystemExit(
            "Error: cyclonedx-py not found. Install dependencies with "
            "'pip install -r requirements.txt'."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        cyclonedx_tool,
        "requirements",
        str(requirements_file),
        "--output-format",
        "JSON",
        "--output-file",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    print(f"SBOM generated at: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
