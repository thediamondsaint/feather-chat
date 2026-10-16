#!/usr/bin/env python3
"""Render the actual app with isolated demo data for a shareable screenshot."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / 'src'))
from backend import Store

output = project / 'previews/FeatherGPT-Omarchy.png'
output.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='feathergpt-showcase-') as folder:
    temp = Path(folder)
    shutil.copytree(project / 'src', temp / 'src', ignore=shutil.ignore_patterns('__pycache__'))
    store = Store(temp / 'data')
    for key, name in [('omarchy', 'Omarchy'), ('writing', 'Writing'), ('ideas', 'Ideas')]:
        store.write('INSERT INTO projects VALUES(?,?,?)', (key, name, ''))
    for title, category in [('Hyprland shortcuts', 'omarchy'), ('Laptop notes', 'omarchy'), ('Draft announcement', 'writing'), ('Weekend projects', 'ideas')]:
        key = store.chat(category)
        store.write('UPDATE chats SET title=? WHERE id=?', (title, key))
    archived = store.chat('omarchy')
    store.write('UPDATE chats SET title=?,archived=1 WHERE id=?', ('Earlier desktop ideas', archived))
    chat = store.chat('omarchy')
    store.write('UPDATE chats SET title=?,updated=? WHERE id=?', ('FeatherGPT on Omarchy · Demo', time.time()+1, chat))
    demo = [
        ('user', 'What is FeatherGPT built for?'),
        ('assistant', '## ChatGPT, a little lighter.\n\n'
         'A native **Quickshell + QtQuick** client for **Omarchy and Hyprland**.\n\n'
         'Keep conversations in **folders**, search local history, or archive old chats and restore them later.'),
        ('user', 'Can I make the workspace my own?'),
        ('assistant', '## Your workspace. Your style.\n\n'
         '- **Four themes:** Forest, Midnight, Plum, and Paper.\n'
         '- **Custom backgrounds:** local images or subtle patterns.\n'
         '- **Gentle effects:** quick transitions with a reduced-motion option.\n\n'
         'Connect an eligible ChatGPT plan to chat. Your local history stays separate from ChatGPT.')
    ]
    for role, content in demo:
        store.write('INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)', (chat, role, content))
    store.db.close()
    snippet = '''
    Timer {
        property int stage: 0
        property int ticks: 0
        interval: 180; running: true; repeat: true
        onTriggered: {
            if (++ticks > 50) { console.error("SHOWCASE_FAILED timeout"); Qt.quit(); return; }
            if (stage === 0 && root.ready) {
                surface.Window.window.width=1180;
                surface.Window.window.height=760;
                Theme.themeId="midnight";
                root.backgroundStyle="contours";
                root.backgroundStrength=12;
                root.selectedProject="omarchy";
                root.refreshList();
                root.call({op:"load",chat:CHAT_ID});
                root.receive({event:"models",rows:[{slug:"demo",name:"Demo preview"}],selected:"demo"});
                stage++;
            } else if (stage === 1 && messages.count === 4 && projectPicker.currentIndex === 3 && chatBackdrop.imageStatus === Image.Ready && !chatReveal.running) {
                composer.focus=false;
                transcript.positionViewAtBeginning();
                stage++;
            } else if (stage === 2) {
                stage++;
                surface.grabToImage(function(result) {
                    if (result.saveToFile(OUTPUT_PATH)) console.log("SHOWCASE_READY");
                    else console.error("SHOWCASE_FAILED save");
                    Qt.quit();
                });
            }
        }
    }
'''.replace('CHAT_ID', json.dumps(chat)).replace('OUTPUT_PATH', json.dumps(str(output)))
    path = temp / 'src/shell.qml'
    path.write_text(path.read_text().rsplit('}', 1)[0] + snippet + '\n}\n')
    runtime = temp / 'runtime'
    runtime.mkdir(mode=0o700)
    env = {**os.environ, 'XDG_RUNTIME_DIR': str(runtime), 'FEATHER_DATA_DIR': str(temp/'data'),
           'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': 'generic',
           'QT_QUICK_CONTROLS_STYLE': 'Basic', 'QT_QUICK_BACKEND': 'software'}
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    process = subprocess.run(['qs', '-p', str(temp/'src'), '--no-color'], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
    if process.returncode or 'SHOWCASE_READY' not in process.stdout or 'SHOWCASE_FAILED' in process.stdout:
        print(process.stdout)
        raise SystemExit(1)
    print(output)
