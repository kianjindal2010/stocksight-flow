# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


datas = [
    ("learner_fastapi_firebase/templates", "learner_fastapi_firebase/templates"),
    ("learner_fastapi_firebase/static", "learner_fastapi_firebase/static"),
]

hiddenimports = (
    collect_submodules("webview")
    + collect_submodules("firebase_admin")
    + collect_submodules("google.cloud.firestore")
    + collect_submodules("google.cloud.firestore_v1")
    # The NVIDIA client is imported defensively so the app can run without
    # AI configured.  Collect it explicitly so PyInstaller does not omit it
    # from a desktop build when an NVIDIA key is configured.
    + collect_submodules("openai")
    + [
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets.websockets_impl",
        "httptools",
        "websockets",
    ]
)

a = Analysis(
    ["learner_fastapi_firebase/desktop.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "torch", "tensorflow", "onnxruntime", "matplotlib", "pyarrow", "openpyxl"],
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
    name="StockSightLearner-Updated",
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
)
