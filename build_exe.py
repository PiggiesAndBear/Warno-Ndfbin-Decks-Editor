# -*- coding: utf-8 -*-
"""Package the editor into a single-file EXE.

    python build_exe.py              # version read from ndfbin_decks/__init__.py
    python build_exe.py 0.2          # explicit override

Run it with the interpreter that has PyInstaller, not with a bare ``python`` —
and keep that interpreter separate from the one you run the editor with, since
the build tooling and the runtime dependencies share nothing::

    py -3 -m venv .venv-build
    .venv-build\\Scripts\\pip install -r requirements.txt -r requirements-build.txt
    .venv-build\\Scripts\\python build_exe.py

Four rules here, each of which cost an afternoon once:

* **The build never writes ``dist/``.**  ``dist/`` holds the last *released*
  binary.  A build that clears it and then fails leaves nothing to fall back
  to, so builds land in ``dist_<ver>/`` and promoting to ``dist/`` is a
  separate, deliberate step (see the README section at the bottom).
* **Every ``--add-data`` and ``--icon`` is an absolute path.**  PyInstaller
  resolves relative ones against the *spec* directory, and the spec lives in
  ``build_<ver>/``, so a relative path points at a folder that does not exist.
  It then prints a single ``WARNING``, does not abort, and still exits 0 — the
  result being an EXE that launches perfectly and is missing its payload.
* **The version has one source**, ``ndfbin_decks/__init__.py``, which is also
  what the running app reports in its log.  Typing it twice is how an artefact
  ends up labelled with a number nobody can trace back.
* **A missing EXE is a failure.**  ``PyInstaller.__main__.run`` returns
  ``None`` whether or not it produced anything, so the exit code of the build
  says nothing about the build.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ndfbin_decks import APP_NAME, APP_TAGLINE      # noqa: E402

#: Qt Python bindings this GUI provably never imports.  Checked against the
#: package: the only Qt imports anywhere are QtCore, QtGui and QtWidgets.
#:
#: Excluding a module here does **not** drop the matching ``Qt6*.dll`` — that
#: is collected by binary dependency analysis — so the platform plugin still
#: has everything it links against.  What it removes is the bulk of the
#: ``PySide6`` python half, which is what the one-file unpack spends its time
#: writing to disk on every single launch.
TRIMMED_QT = [
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets", "PySide6.QtNetwork",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtSensors", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtHttpServer",
]

#: Nothing here is imported; naming them stops PyInstaller from hauling in
#: whatever happens to be installed in the build venv.
TRIMMED_OTHER = ["tkinter", "numpy", "scipy", "pandas", "matplotlib",
                 "PIL", "yaml", "pytest"]


def read_version() -> str:
    """The one place the release number is written down."""
    src = (ROOT / "ndfbin_decks" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', src, re.M)
    if not match:
        raise SystemExit("no __version__ in ndfbin_decks/__init__.py")
    return match.group(1)


def write_version_file(ver: str, path: Path, exe_name: str) -> Path:
    """Author the Windows VERSIONINFO block.

    Written through PyInstaller's own objects rather than by hand so the fixed
    part and the string table cannot disagree about the numbering.  The
    language is 0x0804 / 1200 (Simplified Chinese, UTF-16) because that is what
    the product's own text is in and because a mismatched codepage is how a
    Chinese description turns into mojibake in the Properties dialog.
    """
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
        VarStruct, VSVersionInfo)

    quad = tuple(([int(p) for p in re.findall(r"\d+", ver)] + [0, 0, 0, 0])[:4])
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=quad, prodvers=quad, mask=0x3F, flags=0x0,
                          OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("080404b0", [
                StringStruct("CompanyName", APP_NAME),
                StringStruct("FileDescription", f"{APP_NAME} v{ver}"),
                StringStruct("FileVersion", f"{ver}.0"),
                StringStruct("InternalName", APP_NAME),
                StringStruct("OriginalFilename", exe_name),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", f"{ver}.0"),
                # Shows up in the Properties sheet, which is the one place a
                # tagline can explain itself without a hover to carry it.
                StringStruct("Comments", APP_TAGLINE),
            ])]),
            VarFileInfo([VarStruct("Translation", [2052, 1200])]),
        ])
    path.write_text(str(info), encoding="utf-8")
    return path


def check_bundled(exe: Path, expect: list[tuple[str, str]]) -> list[str]:
    """Read the one-file archive back and assert the payload made it in.

    "It started, so the resources must be there" is exactly the reasoning that
    lets a silently-dropped ``--add-data`` ship.  The archive table is the
    ground truth, and it is cheap to read.

    Two places have to be looked in, and confusing them is why the first
    version of this check reported everything missing: a one-file build puts
    the *data* files in the PKG archive's table, but the pure-Python modules
    are compiled into a nested ``PYZ-00.pyz`` that the table shows as a single
    entry.  A module name therefore never appears at the top level.
    """
    from PyInstaller.archive.readers import CArchiveReader
    reader = CArchiveReader(str(exe))
    data_names = [k.replace("\\", "/") for k in reader.toc]
    modules = set()
    for name in list(reader.toc):
        if name.endswith(".pyz"):
            # Keys are dotted module names (``a.b.c``); normalising to slashes
            # lets one pattern match a payload path or a module alike.
            modules |= {k.replace("\\", "/").replace(".", "/")
                        for k in reader.open_embedded_archive(name).toc}
    print(f"    archive: {len(data_names)} payload entries, "
          f"{len(modules)} frozen modules")
    problems = []
    for pattern, why in expect:
        hits = ([n for n in data_names if pattern in n]
                + [n for n in modules if pattern in n])
        print(f"    {pattern:30s} {len(hits):4d} hits   {why}")
        if not hits:
            problems.append(f"{pattern} missing from the bundle ({why})")
    return problems


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    ver = argv[0] if argv else read_version()
    exe_name = f"{APP_NAME} v{ver}.exe"

    build_dir = ROOT / f"build_{ver}"
    dist_dir = ROOT / f"dist_{ver}"
    for d in (build_dir, dist_dir):
        shutil.rmtree(d, ignore_errors=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    icon = ROOT / "assets" / "app.ico"
    if not icon.is_file():
        print(f"FAILED: no icon at {icon} — run assets/make_icon.py first")
        return 1
    version_file = write_version_file(ver, build_dir / "version_info.txt",
                                      exe_name)

    import PyInstaller.__main__

    print(f"building {exe_name}  (onefile, windowed)")
    args = [
        str(ROOT / "main.py"),
        "--name", exe_name[:-4],
        "--onefile",
        "--windowed",
        "--icon", str(icon),
        # A file (not a directory) as the --add-data source: a lone icon is the
        # whole payload, and shipping `assets/` would drag icon-source.jpg and
        # the preview renders along with it.
        "--add-data", f"{icon}{os.pathsep}assets",
        "--version-file", str(version_file),
        # Found by static analysis anyway, but naming them costs nothing and
        # lz4's submodule is the kind of thing that gets missed.
        "--hidden-import", "zstandard",
        "--hidden-import", "lz4.block",
        # The app imports from the checkout root, not from an installed package.
        "--paths", str(ROOT),
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir / "work"),
        "--specpath", str(build_dir),
        "--noconfirm", "--clean",
    ]
    for mod in TRIMMED_QT + TRIMMED_OTHER:
        args += ["--exclude-module", mod]
    PyInstaller.__main__.run(args)

    exe = dist_dir / exe_name
    if not exe.is_file():
        print(f"FAILED: no artefact at {exe}")
        return 1

    print("\nchecking the bundle:")
    # Patterns are matched against payload paths *and* frozen module names, and
    # the module keys are dotted (``a.b.c``) normalised to slashes — so no
    # ``.py`` suffix belongs in a pattern that is meant to hit a module.
    problems = check_bundled(exe, [
        ("assets/app.ico", "the window icon"),
        ("ndfbin_decks/app/gui", "the GUI itself"),
        ("ndfbin_decks/app/swap_dialog", "the equipment picker"),
        ("ndfbin_decks/io/divisions", "the 师/国家 parser"),
        ("ndfbin_decks/io/unit_universe", "the unit universe"),
        ("ndfbin_decks/core/cndf_codec", "the binary codec"),
        # Binary extensions: not readable as source, so PyInstaller's import
        # analysis is the only thing that can pull them in, and a codec that
        # is missing does not crash — it fails on the first file it opens.
        ("zstandard", "zstd compression for .ndfbin"),
        ("lz4", "lz4 blocks for .dic dictionaries"),
    ])
    digest = hashlib.md5(exe.read_bytes()).hexdigest()
    print(f"\nbuilt  {exe}")
    print(f"size   {exe.stat().st_size:,} bytes")
    print(f"md5    {digest}")
    if problems:
        for p in problems:
            print(f"BUNDLE PROBLEM: {p}")
        return 1
    print(f"\nnext: {Path(sys.executable).with_name('python.exe')} "
          f"verify_exe.py {ver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
