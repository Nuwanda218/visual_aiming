# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]

block_cipher = None


a = Analysis([str(project_root / 'main.py')],
             pathex=[str(project_root), str(project_root / 'src')],
             binaries=[],
             datas=[(str(project_root / 'config.json'), '.'), (str(project_root / 'models'), 'models')],
             hiddenimports=['cv2', 'numpy', 'pyautogui', 'keyboard', 'mss', 'pkg_resources.py2_warn', 'setuptools'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='aim_assist',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )
