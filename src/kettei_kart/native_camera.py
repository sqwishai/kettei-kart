"""Build and validate the pinned engine's camera bridge; never choose game controls."""

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

ENGINE_VERSION = "0.7.4"
ENGINE_COMMIT = "dd70f6823f248ae1df2ce513839a9b2c8c940c39"
ENGINE_REPOSITORY = "https://github.com/bpiwowar/pystk2.git"
SOURCE = Path(__file__).with_name("native") / "camera_control.cpp"


def cache_directory() -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser()
    return cache / "kettei-kart" / "native" / ENGINE_VERSION / platform.machine()


def check_engine() -> None:
    if platform.system() != "Linux":
        raise RuntimeError("Native camera capture currently supports Linux, including WSL2.")
    if importlib.metadata.version("PySuperTuxKart2") != ENGINE_VERSION:
        raise RuntimeError(f"Native camera capture requires PySuperTuxKart2=={ENGINE_VERSION}.")


def build(compiler: str = "g++", source: Path | None = None) -> Path:
    """Compile the small bridge against an unmodified, pinned source checkout."""
    check_engine()
    executable = shutil.which(compiler)
    if not executable:
        raise RuntimeError("Install a C++ compiler: sudo apt-get install g++ git")
    cache = cache_directory()
    cache.mkdir(parents=True, exist_ok=True)
    upstream = source.resolve() if source else cache / "pystk2"
    if not upstream.exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "v0.7.4",
                ENGINE_REPOSITORY,
                str(upstream),
            ],
            check=True,
        )
    commit = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(upstream), "diff", "HEAD", "--name-only"], text=True
    ).strip()
    if commit != ENGINE_COMMIT or dirty:
        raise RuntimeError("Camera headers must match the unmodified, pinned engine commit.")
    target = cache / "camera_control.so"
    temporary = cache / "camera_control.building.so"
    subprocess.run(
        [
            executable,
            "-std=c++14",
            "-O2",
            "-DNDEBUG",
            "-DPYSTK_BUILD",
            "-fPIC",
            "-shared",
            f"-I{upstream / 'src'}",
            f"-I{upstream / 'lib/irrlicht/include'}",
            f"-I{upstream / 'lib/bullet/src'}",
            f"-I{upstream / 'lib/graphics_engine/include'}",
            str(SOURCE),
            "-o",
            str(temporary),
        ],
        check=True,
    )
    temporary.replace(target)
    receipt = dict(
        engine_version=ENGINE_VERSION,
        engine_commit=commit,
        platform=platform.machine(),
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    target.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    return target


def load_bridge(stk):
    check_engine()
    target = cache_directory() / "camera_control.so"
    if not target.exists() or not target.with_suffix(".json").exists():
        raise RuntimeError("Build camera support first: python -m kettei_kart.native_camera")
    receipt = json.loads(target.with_suffix(".json").read_text())
    expected = dict(
        engine_version=ENGINE_VERSION,
        engine_commit=ENGINE_COMMIT,
        platform=platform.machine(),
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
    )
    if receipt != expected:
        raise RuntimeError("Native camera receipt does not match; rebuild camera support.")
    ctypes.CDLL(stk.__file__, mode=ctypes.RTLD_GLOBAL)
    native = ctypes.CDLL(str(target))
    pointer = ctypes.POINTER(ctypes.c_float)
    for method in (native.kart_camera_get, native.kart_camera_set, native.kart_camera_info):
        method.argtypes, method.restype = [ctypes.c_uint, pointer], ctypes.c_int
    native.kart_camera_set_aspect.argtypes = [ctypes.c_uint, ctypes.c_float]
    native.kart_camera_set_aspect.restype = ctypes.c_int
    native.kart_replay_set_hue.argtypes = [ctypes.c_uint, ctypes.c_float]
    native.kart_replay_set_hue.restype = ctypes.c_int
    native.kart_replay_label.argtypes = [ctypes.c_uint, ctypes.c_char_p]
    native.kart_replay_label.restype = ctypes.c_int
    native.kart_camera_count.argtypes, native.kart_camera_count.restype = [], ctypes.c_int
    native.kart_camera_clear_start_signal.argtypes = []
    native.kart_camera_clear_start_signal.restype = ctypes.c_int
    return native, receipt


class CameraGuard:
    """Require a fixed player identity and square-pixel projection for every capture."""

    def __init__(self, stk, kart_ids: tuple[int, ...], aspect: float):
        self.native, self.receipt = load_bridge(stk)
        self.kart_ids, self.aspect = kart_ids, aspect
        if self.native.kart_camera_count() != len(kart_ids):
            raise RuntimeError("The native camera count does not match the player count")
        for slot in range(len(kart_ids)):
            if not self.native.kart_camera_set_aspect(slot, aspect):
                raise RuntimeError("The native camera rejected its output aspect ratio")
            self.validate(slot, aspect)

    def validate(self, slot: int, frame_aspect: float) -> None:
        values = (ctypes.c_float * 4)()
        if not self.native.kart_camera_info(slot, values):
            raise RuntimeError("The player's native camera is unavailable")
        if int(values[1]) != self.kart_ids[slot]:
            raise RuntimeError("Camera ownership changed; refusing to send another kart's view")
        if abs(values[0] - frame_aspect) > 1e-5 or abs(frame_aspect - self.aspect) > 1e-5:
            raise RuntimeError("Camera projection does not match the captured frame aspect ratio")

    def manifest(self) -> dict:
        return dict(
            protocol="fixed-player-cameras-v1",
            player_kart_ids=list(self.kart_ids),
            projection_aspect=self.aspect,
            ownership_checked_every_capture=True,
            native_bridge=self.receipt,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--source", type=Path, help="Existing, unmodified v0.7.4 source checkout")
    args = parser.parse_args()
    print(f"Camera support built: {build(args.compiler, args.source)}")


if __name__ == "__main__":
    main()
