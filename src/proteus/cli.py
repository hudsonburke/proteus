"""CLI for building Proteus parametric parts from Melos assembly specs.

Usage:
    proteus build spec.json -o output.stl
    proteus build spec.json -o output.step
    cat spec.json | proteus build -o output.stl

The spec JSON is the resolved output from Melos's
``POST /model/assembly/{name}/build`` endpoint — the zero-coupling protocol
between the two packages.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import build123d as bd

# ── Part class registry ───────────────────────────────────────────────────
# Maps part_type string (from Melos assembly spec) to Proteus class.
# Extend this as new components are added to Proteus.

_PART_REGISTRY: dict[str, type[Any]] = {}

def register_part(part_type: str) -> type[Any]:
    """Class decorator that registers a part type for the CLI."""
    def _inner(cls: type[Any]) -> type[Any]:
        _PART_REGISTRY[part_type] = cls
        return cls
    return _inner


# ── CLI ───────────────────────────────────────────────────────────────────


def add_parser(subparsers: Any) -> None:
    """Register the 'build' subcommand (argparse style)."""
    from argparse import ArgumentParser
    parser = subparsers.add_parser(
        "build",
        help="Build a Proteus part from a Melos assembly spec JSON",
    )
    parser.add_argument(
        "spec",
        nargs="?",
        help="Path to JSON spec file (omit or '-' for stdin)",
    )
    parser.add_argument(
        "-o", "--output",
        default="output.stl",
        help="Output file path (extension determines format: .stl / .step)",
    )
    parser.add_argument(
        "--export-attachments",
        type=str,
        default=None,
        help="Optional: export attachment positions to a JSON file",
    )
    return parser


def build_from_spec(spec: dict[str, Any], output_path: str, export_attachments: str | None = None) -> None:
    """Build one or more Proteus parts from a resolved Melos assembly spec.

    Parameters
    ----------
    spec:
        The resolved assembly JSON — either a single part dict or a full
        assembly dict with a "parts" array.
    output_path:
        File path for the exported geometry.  Extension selects format.
    export_attachments:
        Optional path for a JSON file with attachment world positions.
    """
    import logging
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("proteus")

    # Normalise: accept either a single part or an assembly
    parts: list[dict[str, Any]] = []
    if "parts" in spec:
        parts = spec["parts"]
    elif "part_type" in spec:
        parts = [spec]
    else:
        log.warning("Spec has no 'parts' array or 'part_type'; treating as part list root")
        parts = [spec]

    built_parts: list[bd.Shape] = []
    all_attachments: dict[str, Any] = {}
    failed_parts: list[str] = []

    for idx, part_spec in enumerate(parts):
        part_type = part_spec.get("part_type", "Unknown")
        part_id = part_spec.get("id", f"part_{idx}")
        parameters = part_spec.get("parameters", {})
        measurements = part_spec.get("measurements", {})
        attachments = part_spec.get("attachments", {})

        # Look up the Proteus class
        cls = _PART_REGISTRY.get(part_type)
        if cls is None:
            log.warning("Unknown part type '%s' for '%s' — skipping", part_type, part_id)
            failed_parts.append(part_id)
            continue

        # If the part accepts a limb_circumference parameter and we have
        # a length measurement, derive circumference from limb radius.
        # (This is the key sizing step that the user described.)
        params = dict(parameters)
        if hasattr(cls, "limb_circumference") and measurements:
            # Use the first available measurement as a circumference proxy.
            # In a real design, which measurement maps to circumference
            # is part-specific and should be encoded in the descriptor.
            for seg, length_m in measurements.items():
                # Convert metres to mm
                length_mm = length_m * 1000.0
                # For a cuff, circumference ≈ 2 * length (rough approximation)
                # Real circumference should come from the subject's actual
                # limb measurement, not derived from landmark distance.
                # This is a placeholder that the user refines per part.
                if "circumference" not in params and length_mm > 0:
                    params["limb_circumference"] = length_mm * 2.0
                    log.info(
                        "%s: derived limb_circumference=%.1f mm from %s=%.3f m",
                        part_id, params["limb_circumference"], seg, length_m,
                    )
                    break

        try:
            log.info("Building %s (%s)…", part_id, part_type)
            instance = cls(**params)
            built_parts.append(instance.geom)
            log.info("  ✓ %s built: %s", part_id, type(instance.geom).__name__)
        except Exception as e:
            log.error("  ✗ %s failed: %s", part_id, e)
            failed_parts.append(part_id)
            continue

        # Record attachments
        if attachments:
            all_attachments[part_id] = attachments

    if not built_parts:
        log.error("No parts were built successfully")
        sys.exit(1)

    # Export the geometry
    out_path = Path(output_path)
    ext = out_path.suffix.lower()

    if ext == ".stl":
        # Combine multiple parts into a compound and export
        if len(built_parts) == 1:
            compound = built_parts[0]
        else:
            compound = bd.Compound(label="assembly", children=built_parts)
        bd.export_stl(compound, str(out_path))
        log.info("Exported STL: %s (%d parts)", out_path, len(built_parts))

    elif ext == ".step":
        compound = bd.Compound(label="assembly", children=built_parts) if len(built_parts) > 1 else built_parts[0]
        bd.export_step(compound, str(out_path))
        log.info("Exported STEP: %s", out_path)

    elif ext in (".brep", ".brepb"):
        compound = bd.Compound(label="assembly", children=built_parts) if len(built_parts) > 1 else built_parts[0]
        bd.export_brep(compound, str(out_path))
        log.info("Exported BREP: %s", out_path)

    else:
        log.warning("Unknown extension '%s', falling back to STL", ext)
        bd.export_stl(built_parts[0], str(out_path))

    # Export attachments if requested
    if export_attachments and all_attachments:
        att_path = Path(export_attachments)
        with open(att_path, "w") as f:
            json.dump(all_attachments, f, indent=2)
        log.info("Exported attachments: %s (%d parts)", att_path, len(all_attachments))

    if failed_parts:
        log.warning("Failed parts: %s", ", ".join(failed_parts))


def main() -> None:
    """Proteus CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="proteus",
        description="Parametric CAD part builder — build from Melos assembly specs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand")

    # Register subcommands
    build_parser = add_parser(subparsers)

    args = parser.parse_args()

    if args.command == "build":
        # Read spec from file or stdin
        if args.spec and args.spec != "-":
            with open(args.spec) as f:
                spec = json.load(f)
        else:
            spec = json.load(sys.stdin)

        build_from_spec(
            spec,
            args.output,
            export_attachments=args.export_attachments,
        )
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
