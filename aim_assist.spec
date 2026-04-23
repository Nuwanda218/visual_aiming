# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['main.py'],
             pathex=['F:\\PyCharm\\python-code\\脚本\\瞄准吸附'],
             binaries=[],
             datas=[('config.json', '.'), ('color_thresholds.txt', '.')],
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
