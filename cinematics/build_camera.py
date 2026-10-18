"""Build the optional native camera bridge against the simulator's pinned headers."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE_VERSION = "0.7.4"
ENGINE_COMMIT = "dd70f6823f248ae1df2ce513839a9b2c8c940c39"
ENGINE_REPOSITORY = "https://github.com/bpiwowar/pystk2.git"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--source", type=Path, help="Existing, unmodified v0.7.4 source checkout")
    args = parser.parse_args()
    if platform.system() != "Linux":
        raise SystemExit("The optional camera bridge currently supports Linux, including WSL2.")
    if importlib.metadata.version("PySuperTuxKart2") != ENGINE_VERSION:
        raise SystemExit(f"Install PySuperTuxKart2=={ENGINE_VERSION} before building.")
    compiler = shutil.which(args.compiler)
    if not compiler:
        raise SystemExit("A C++ compiler is required. On Ubuntu: sudo apt-get install g++")
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    source = args.source.resolve() if args.source else cache / "pystk2"
    if not source.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", "v0.7.4", ENGINE_REPOSITORY, str(source)],
            check=True,
        )
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True
    )
    if commit != ENGINE_COMMIT or dirty.strip():
        raise SystemExit("Camera headers must match the unmodified, pinned v0.7.4 commit.")
    target = cache / "camera_control.so"
    subprocess.run(
        [
            compiler,
            "-std=c++14",
            "-O2",
            "-DNDEBUG",
            "-DPYSTK_BUILD",
            "-fPIC",
            "-shared",
            f"-I{source / 'src'}",
            f"-I{source / 'lib/irrlicht/include'}",
            f"-I{source / 'lib/bullet/src'}",
            str(ROOT / "camera_control.cpp"),
            "-o",
            str(target),
        ],
        check=True,
    )
    receipt = {
        "engine_version": ENGINE_VERSION,
        "engine_commit": commit,
        "platform": platform.machine(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    target.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Camera bridge built: {target}")


if __name__ == "__main__":
    main()
