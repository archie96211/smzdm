# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import pathlib
import site
import sys

from PyInstaller.depend import bindepend

ROOT = Path.cwd()


def _get_accessible_site_paths():
    orig_paths = list(site.getsitepackages())
    try:
        orig_paths.append(site.getusersitepackages())
    except Exception:
        pass

    excluded_paths = {
        pathlib.Path(sys.base_prefix),
        pathlib.Path(sys.base_prefix).resolve(),
        pathlib.Path(sys.prefix),
        pathlib.Path(sys.prefix).resolve(),
    }

    resolved_paths = []
    for path in orig_paths:
        try:
            resolved_paths.append(pathlib.Path(path).resolve())
        except OSError:
            pass
    orig_paths += resolved_paths

    paths = set()
    for path in orig_paths:
        if not path:
            continue
        path = pathlib.Path(path)
        try:
            if not path.is_dir():
                continue
        except OSError:
            continue
        if path in excluded_paths:
            continue
        paths.add(path)

    return sorted(paths, key=lambda x: len(x.parents), reverse=True)


bindepend._get_paths_for_parent_directory_preservation = _get_accessible_site_paths


a = Analysis(
    ['desktop_app.py'],
    pathex=[str(ROOT)],
    binaries=[('wechat_bridge/smzdm_wechat_bridge.exe', 'wechat_bridge')],
    datas=[('static', 'static')],
    hiddenimports=[
        'pystray._win32',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['data', 'logs', 'node_modules', 'frontend', '.venv'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='smzdm_monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='smzdm_monitor',
)
