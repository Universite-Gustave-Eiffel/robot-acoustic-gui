# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=[('src/controller_interface/config.ini', 'controller_interface'), ('src/labshop_interface/config.ini', 'labshop_interface'), ('src/labshop_interface/pulse_projects', 'labshop_interface/pulse_projects'), ('src/labshop_interface/mesures_pulse_ascii', 'labshop_interface/mesures_pulse_ascii'), ('src/gui/new_icons', 'gui/new_icons')],
    hiddenimports=['comtypes.gen._98BA4851_F724_11CE_9645_0020AF34D7AC_0_1_0'],
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
    name='RobotAcousticGUI',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RobotAcousticGUI',
)
