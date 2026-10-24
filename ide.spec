# ide.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import webui

block_cipher = None
webui_dll = Path(webui.__file__).resolve().parent / 'webui-windows-msvc-x64' / 'webui-2.dll'
if not webui_dll.is_file():
    raise FileNotFoundError(f'WebUI runtime DLL not found: {webui_dll}')

# ==========================================
# Собираем скрытые импорты для FastAPI и Uvicorn
# ==========================================
hiddenimports = []
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')
hiddenimports += collect_submodules('pydantic')

hiddenimports += [
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan.on',
    'winpty',
    'winpty.cywinpty',
    'fastapi_server',
]

a = Analysis(
    ['test_main.py'],
    pathex=[],
    
    # Бинарники оставляем пустыми, всё нужное кладем в datas
    binaries=[],
    
    # ==========================================
    # РЕСУРСЫ И DLL
    # ==========================================
    datas=[
        ('index.html', '.'),
        
        # Keep the WebUI runtime available beside the executable and in PyInstaller's resource directory.
        (str(webui_dll), '.'),
        
        (str(webui_dll), '_internal'),
    ],
    
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    
    includes=[
        'winpty',
        'winpty.cywinpty',
        'webui',
    ],
    
    # ==========================================
    # ИСКЛЮЧАЕМ ТЯЖЕЛЫЕ БИБЛИОТЕКИ
    # ==========================================
    excludes=[
        'torch', 'torchvision', 'torchaudio', 
        'tensorboard', 'tensorflow', 
        'matplotlib', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook',
        'PIL', 'cv2', 'sklearn', 'numba',
    ],
    
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ==========================================
# РЕЖИМ ONEDIR (Папка)
# ==========================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MyIDE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,             # Оставь True для отладки
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',   # Отключает создание отдельной папки _internal на верхнем уровне (если нужно)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MyIDE',
)