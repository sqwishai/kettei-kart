"""Prepare a separate daytime scene for pre-race cinematics."""

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def prepare() -> Path:
    """Keep the simulator's downloaded assets untouched; change copied scene XML only."""
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    source = cache / "PySuperTuxKart2/1.5/data"
    if not source.is_dir():
        raise FileNotFoundError("Run a normal kettei-kart race first to download the game assets.")
    runtime = ROOT / ".cache/daylight"
    if (runtime / "manifest.json").exists():
        return runtime
    sky = ROOT / "rainbow-sky.png"
    runtime.mkdir(parents=True, exist_ok=False)
    data = runtime / "data"
    data.mkdir()
    for item in source.iterdir():
        if item.name != "tracks":
            (data / item.name).symlink_to(item, target_is_directory=item.is_dir())
    (data / "tracks").mkdir()
    hashes = {}
    for track in (source / "tracks").iterdir():
        target = data / "tracks" / track.name
        scene_file = track / "scene.xml"
        if not scene_file.is_file():
            target.symlink_to(track, target_is_directory=track.is_dir())
            continue
        target.mkdir()
        for item in track.iterdir():
            if item.name != "scene.xml":
                (target / item.name).symlink_to(item, target_is_directory=item.is_dir())
        scene = ET.parse(scene_file)
        root = scene.getroot()
        # Disable only the non-colliding nighttime beacon in daytime cinematics.
        for effect in list(root.findall("object")):
            if effect.get("model") == "lightBeam.spm":
                if effect.get("interaction") != "ghost":
                    raise ValueError("Refusing to remove a collidable scene object")
                root.remove(effect)
        sun = root.find("sun")
        if sun is not None:
            sun.attrib.update(
                {
                    "fog": "false",
                    "fog-max": "0",
                    "sun-diffuse": "180 185 175",
                    "ambient": "90 110 120",
                }
            )
        for tag in ("sky-box", "sky-dome", "sky-color"):
            for old in root.findall(tag):
                root.remove(old)
        ET.SubElement(root, "sky-color", {"rgb": "68 175 255"})
        ET.SubElement(
            root,
            "sky-dome",
            {
                "texture": "kettei-rainbow-sky.png",
                "horizontal": "32",
                "vertical": "16",
                "texture-percent": "1.0",
                "sphere-percent": "1.3",
                "speed-x": "0.0",
                "speed-y": "0.0",
            },
        )
        (target / "kettei-rainbow-sky.png").symlink_to(sky)
        original = hashlib.sha256(scene_file.read_bytes()).hexdigest()
        scene.write(target / "scene.xml", encoding="utf-8", xml_declaration=True)
        if hashlib.sha256(scene_file.read_bytes()).hexdigest() != original:
            raise RuntimeError("Original game scene changed")
        hashes[track.name] = original
    (runtime / "manifest.json").write_text(
        json.dumps(
            {
                "purpose": "Presentation-only intro",
                "original_scene_sha256": hashes,
                "sky_sha256": hashlib.sha256(sky.read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    return runtime


def graphics(stk, width: int = 640, height: int = 360):
    config = stk.GraphicsConfig.hd()
    config.screen_width, config.screen_height = width, height
    config.motionblur = config.dof = config.bloom = config.glow = False
    config.light_shaft = config.display = False
    return config
