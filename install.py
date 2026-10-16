#!/usr/bin/env python3
"""Install for the current user. No root access or package downloads."""
import os
from pathlib import Path
import shutil
import shlex

root=Path(__file__).resolve().parent
home=Path.home()
data=Path(os.environ.get('XDG_DATA_HOME',home/'.local/share'))
app=data/'feather-chat/app'
bindir=home/'.local/bin'
applications=data/'applications'
icons=data/'icons/hicolor/scalable/apps'
for folder in (app,bindir,applications,icons): folder.mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'src',app,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copy2(root/'src/assets/feather.svg',icons/'feather-chat.svg')
shutil.copy2(root/'src/assets/feather.svg',icons/'feathergpt.svg')
launcher=bindir/'feathergpt'
launcher.write_text('''#!/bin/sh
# Keep Qt on its small Basic controls style; use the native Wayland renderer.
export QT_QUICK_CONTROLS_STYLE=Basic
export QT_QPA_PLATFORM=wayland
export QT_QPA_PLATFORMTHEME=generic
appdir='''+shlex.quote(str(app))+'''
if qs ipc -p "$appdir" call window show >/dev/null 2>&1; then
    if command -v hyprctl >/dev/null 2>&1; then
        hyprctl dispatch focuswindow 'title:^(FeatherGPT|Feather Chat)$' >/dev/null 2>&1
    fi
    exit 0
fi
exec qs --no-duplicate -p "$appdir" "$@"
''')
launcher.chmod(0o755)
# Keep old launch commands and pinned desktop entries working after the rename.
legacy_launcher=bindir/'feather-chat'
legacy_launcher.write_text(launcher.read_text())
legacy_launcher.chmod(0o755)
# Desktop Exec uses its own quoting rules, not shell quoting.
quoted='"'+str(launcher).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')+'"'
(applications/'feather-chat.desktop').write_text(f'''[Desktop Entry]
Type=Application
Name=FeatherGPT
GenericName=Lightweight ChatGPT client
Comment=Native ChatGPT client with local folders and archives
Exec={quoted}
Icon=feathergpt
Terminal=false
Categories=Network;Chat;
Keywords=ChatGPT;OpenAI;AI;Feather;FeatherGPT;
StartupNotify=true
''')
if shutil.which('update-desktop-database'):
    import subprocess
    subprocess.run(['update-desktop-database',str(applications)],check=False)
print('Installed FeatherGPT.')
print('Open FeatherGPT from the application launcher, or run: '+str(launcher))
print('History and account files: '+str(data/'feather-chat'))
