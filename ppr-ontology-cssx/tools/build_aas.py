"""Build a full AAS JSON from a compact config file.

Usage:
    python tools/build_aas.py <config.json> [output.aas.json]

Defaults output to aas_configs/generated/<system_id>.aas.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_WORKSPACE = _HERE.parent
sys.path.insert(0, str(_WORKSPACE))

from generation.AAS_generation.cli.generate_aas import AASGenerator


def build(config_path: Path, output_path: Path | None = None) -> Path:
    generator = AASGenerator(str(config_path))
    aas_dict = generator.generate_system(system_id="unused", config={})

    if output_path is None:
        out_dir = _WORKSPACE / "aas_configs" / "generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{generator.system_id}.aas.json"

    output_path.write_text(json.dumps(aas_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Written: {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/build_aas.py <config.json> [output.aas.json]")
        sys.exit(1)

    cfg = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    build(cfg, out)
