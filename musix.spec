# -*- mode: python ; coding: utf-8 -*-
import argparse
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from platform import system, machine
import pathlib

# Build mode is chosen via args after `--`, per the canonical PyInstaller
# pattern (see: https://pyinstaller.org/en/stable/spec-files):
#   pyinstaller musix.spec               -> onefile (single executable)
#   pyinstaller musix.spec -- --onedir   -> onedir at dist/musix/
parser = argparse.ArgumentParser()
parser.add_argument("--onedir", action="store_true",
                    help="Build as a directory tree instead of a single executable")
options = parser.parse_args()

# Pull in every musix submodule unconditionally, so PyInstaller does not
# have to discover the imports one by one.
hiddenimports = collect_submodules('musix')
datas = [('client.zip', '.'), ('version.txt', '.')]
datas += collect_data_files('musix', True, excludes=['**/*.py'], includes=['**/*.*'])
datas += collect_data_files('flask_openapi3', True, excludes=['**/*.py'], includes=['**/*.*'])

def getFlaskOpenApiPath():
    return importlib.resources.files("flask_openapi3")


binary_name = f'musix_{system().lower()}_{machine().lower()}'

a = Analysis(
    ['run.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if options.onedir:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=binary_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=[pathlib.Path('src\\musix\\assets\\logo-fill.light.ico')],
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='musix',
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=binary_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=[pathlib.Path('src\\musix\\assets\\logo-fill.light.ico')],
    )
