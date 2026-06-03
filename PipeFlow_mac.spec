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
    [],
    exclude_binaries=True,
    name="PipeFlow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["pipeflow.icns"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PipeFlow",
)
app = BUNDLE(
    coll,
    name="PipeFlow.app",
    icon="pipeflow.icns",
    bundle_identifier="local.pipeflow.app",
    version="2.0.1",
    info_plist={
        "CFBundleShortVersionString": "2.0.1",
        "CFBundleVersion": "2.0.1",
    },
)
