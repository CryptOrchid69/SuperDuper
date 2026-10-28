# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['SuperDuper.py'],
    pathex=[],
    binaries=[
        ('WinDivert.dll', '.'),
        ('WinDivert64.sys', '.'),
    ],
    datas=[
        ('WinDivert-LICENSE.txt', '.'),
        ('superduper.package.json', '.'),
        ('lips.png', '.'),
    ],
    hiddenimports=['pythoncom', 'pywintypes', 'win32com.client'],
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
    name='SuperDuper',
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
    icon=['SuperDuper.ico'],
    uac_admin=False,
)
