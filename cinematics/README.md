# Pre-race camera introduction

This optional tool films a four-second introduction in the native game: a front view
of the two drivers, followed by a 180-degree camera move into the first player's
driving view. The karts keep their original orientation. It makes no model calls.

After installing the harness and running a race once to download the game assets:

```bash
sudo apt-get install -y g++ git
python cinematics/build_camera.py
python cinematics/intro.py --track lighthouse --seed 501 --output runs/lighthouse-intro.mp4
```

Use `--track olivermath --seed 502` or `--track hacienda --seed 503` for the other
demonstration tracks. Add `--swap` when the race places Jev in the first grid slot.
The camera ends behind the first grid slot. Each invocation requires a fresh process.

The camera bridge calls the engine's native camera API. Its build is pinned to the
same PySuperTuxKart2 0.7.4 source commit as the installed simulator. Its build receipt
records the binary hash; the filming command checks that receipt before loading it.
No binaries or third-party engine source are stored in this repository.

Daylight scenes are built in an ignored local cache using copied scene descriptions
and links to the original assets. The original asset cache is never edited. The
nighttime lighthouse beacon is omitted from this daytime introduction. The road,
drivers and kart geometry remain the native game's assets. A generated sky texture
provides the presentation background. The filming command records the camera path
and verifies that the karts' heading stays unchanged during the shot.

This is a separately filmed introduction. Evaluation uses the ordinary camera and
original scene. Full-race replays must pass the harness's recorded-physics checks;
the cinematic scene should not be substituted into an evaluated race.

The Python orchestration is covered by the repository's Apache-2.0 license.
The shared [camera bridge](../src/kettei_kart/native/camera_control.cpp), which
uses the GPL engine headers, is GPL-3.0-or-later; its accompanying `COPYING`
contains that license. Kettei has mint-green kart paint and Jev has pink, with
compact native name labels. These are presentation changes only. The sky was generated with the
built-in image-generation tool for this project, from a brief for a clear cartoon
sky with rounded clouds, a pastel rainbow, subtle cloud-unicorn shapes and no fog,
text or logos. It is a new presentation asset, separate from the game's assets.
