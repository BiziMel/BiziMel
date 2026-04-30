# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ["pipeflow_desktop.py"],
    pathex=["vendor"],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
        ("dropdown_values.py", "."),
        ("vendor", "vendor"),
    ],
    hiddenimports=[
        "excel_exporter",
        "models",
        "openpyxl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PipeFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="static/favicon.ico",
    version="windows_version_info.txt",
)
