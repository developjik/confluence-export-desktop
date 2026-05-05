# PyInstaller onedir spec for the PySide6 GUI app.
# Build from repository root with:
#   python -m PyInstaller packaging\confluence-export-desktop.spec

block_cipher = None
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
ASSETS = ROOT / "src" / "confluence_sync_tool" / "assets"
APP_ICON = ASSETS / "app.ico"

a = Analysis(
    [str(ROOT / "scripts" / "gui_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(APP_ICON), "confluence_sync_tool/assets"),
        (str(ASSETS / "app-32.png"), "confluence_sync_tool/assets"),
        (str(ASSETS / "app-256.png"), "confluence_sync_tool/assets"),
    ],
    hiddenimports=[*collect_submodules("confluence_markdown_exporter")],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="confluence-export-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(APP_ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="confluence-export-desktop",
)
