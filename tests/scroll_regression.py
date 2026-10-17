#!/usr/bin/env python3
"""Exercise real streamed-message layout and wheel/scrollbar input in Quickshell."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project/'src'))
from backend import Store

with tempfile.TemporaryDirectory(prefix='feathergpt-scroll-') as folder:
    temp = Path(folder)
    shutil.copytree(project/'src', temp/'src', ignore=shutil.ignore_patterns('__pycache__'))
    db = Store(temp/'data')
    chat = db.chat()
    for i in range(64):
        db.write('INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)',
                 (chat, 'assistant' if i % 2 else 'user', f'Message {i}\n' + 'Earlier conversation context. '*20))
    mid = db.write("INSERT INTO messages(chat_id,role,content) VALUES(?,'assistant','## Latest reply\n')", (chat,))
    other = db.chat()
    db.write("INSERT INTO messages(chat_id,role,content) VALUES(?,'user','Another conversation')", (other,))
    db.db.close()
    code = '''
    property int testPinCalls: 0
    TestCase { id: input; name: "ScrollInput"; when: false; optional: true }
    Timer {
        property int stage: 0
        property int ticks: 0
        property int chunks: 0
        property int idlePins: 0
        property int idleTicks: 0
        property real readingY: 0
        property real beforeWheelY: 0
        interval: 70; running: true; repeat: true
        function check(ok, message) {
            if (!ok) { console.error("SCROLL_FAILURE " + message + " y=" + transcript.contentY + " h=" + transcript.contentHeight + " origin=" + transcript.originY + " moving=" + transcript.moving + " view=" + transcript.height + " following=" + root.followLatest); Qt.quit(); throw new Error(message); }
        }
        function tail(message) { check(transcript.atYEnd, message); }
        function delta(text) { root.receive({event:"delta",chat:CHAT,id:MID,text:text}); }
        onTriggered: {
            if (++ticks > 180) { check(false,"timeout at stage " + stage); return; }
            if (stage === 0 && root.ready) {
                Theme.effects=false;
                root.call({op:"load",chat:CHAT}); stage++;
            } else if (stage === 1 && messages.count === 40) {
                check(root.olderMessages,"pagination fixture missing");
                messages.setProperty(messages.count-1,"status","streaming");
                root.bottom(); stage++;
            } else if (stage === 2) {
                tail("initial conversation load");
                delta("First large chunk.\\n".repeat(100)); stage++;
            } else if (stage === 3) {
                tail("reply grew beyond the viewport");
                delta("\\n**Streaming paragraph** with enough words to wrap across the line. ".repeat(8));
                chunks++;
                if (chunks === 5) composer.text="Draft\\n".repeat(8);
                if (chunks === 10) surface.Window.window.width=700;
                if (chunks === 15) { surface.Window.window.width=1000; composer.text=""; }
                if (chunks === 20) stage++;
            } else if (stage === 4) {
                tail("large reply after resize");
                beforeWheelY=transcript.contentY;
                // Queue a pin, then interrupt it with a real upward wheel event.
                delta("\\nQueued text before scrolling up.");
                input.mouseWheel(transcript,transcript.width-32,transcript.height/2,0,360,Qt.NoButton,Qt.NoModifier,0);
                stage++;
            } else if (stage === 5 && !transcript.moving) {
                check(!root.followLatest,"wheel up did not pause following");
                check(transcript.contentY < beforeWheelY-10,"wheel up did not scroll");
                check(latestButton.visible,"Latest button missing");
                readingY=transcript.contentY;
                delta("\\nMore text while reading history. ".repeat(40)); stage++;
            } else if (stage === 6) {
                check(!root.followLatest,"stream resumed following without input");
                check(Math.abs(transcript.contentY-readingY)<3,"new tokens moved the reading position");
                input.mouseClick(latestButton,latestButton.width/2,latestButton.height/2,Qt.LeftButton,Qt.NoModifier,0);
                stage++;
            } else if (stage === 7) {
                check(root.followLatest,"Latest did not resume following");
                tail("Latest did not reach bottom");
                let thumb=transcriptScroll.contentItem;
                let p=thumb.mapToItem(transcriptScroll,thumb.width/2,thumb.height/2);
                input.mouseDrag(transcriptScroll,p.x,p.y,0,-140,Qt.LeftButton,Qt.NoModifier,5);
                stage++;
            } else if (stage === 8 && !transcript.moving) {
                check(!root.followLatest,"scrollbar drag did not pause following");
                check(!transcript.atYEnd,"scrollbar drag did not leave bottom");
                readingY=transcript.contentY;
                delta("\\nMore text after dragging the scrollbar. ".repeat(30)); stage++;
            } else if (stage === 9) {
                check(Math.abs(transcript.contentY-readingY)<3,"stream fought the scrollbar");
                // Returning the thumb to the end must re-enable automatic following.
                let thumb=transcriptScroll.contentItem;
                let p=thumb.mapToItem(transcriptScroll,thumb.width/2,thumb.height/2);
                input.mouseDrag(transcriptScroll,p.x,p.y,0,transcriptScroll.height-p.y-2,Qt.LeftButton,Qt.NoModifier,5);
                stage++;
            } else if (stage === 10) {
                check(root.followLatest,"returning scrollbar to bottom did not resume");
                delta("\\nFinal paragraph.\\n\\n- A Markdown list\\n- Another item\\n\\n```python\\nprint('finished')\\n```\\n");
                root.receive({event:"finished",chat:CHAT,id:MID,status:"complete"}); stage++;
            } else if (stage === 11) {
                tail("final Markdown reflow lost the bottom");
                check(root.followLatest,"Markdown stopped following");
                root.call({op:"load",chat:CHAT,before:messages.get(0).key}); stage++;
            } else if (stage === 12 && messages.count === 65) {
                check(!root.followLatest,"loading earlier messages must pause following");
                check(!transcript.atYEnd,"earlier history jumped to the newest reply");
                root.bottom(); stage++;
            } else if (stage === 13) {
                tail("Latest after loading earlier history");
                root.call({op:"load",chat:OTHER}); stage++;
            } else if (stage === 14 && root.chatId === OTHER) {
                check(root.followLatest,"new conversation did not reset following");
                check(messages.count === 1,"wrong conversation data");
                idlePins=root.testPinCalls; stage++;
            } else if (stage === 15) {
                check(root.testPinCalls === idlePins,"tail pin kept running while idle");
                if (++idleTicks === 5) {
                    console.log("SCROLL_SUCCESS long stream, viewport resize, draft resize, real wheel input, queued pin cancellation, real scrollbar drag, Latest, Markdown reflow, older pages, conversation switch, no idle pin loop");
                    Qt.quit();
                }
            }
        }
    }
'''.replace('CHAT', json.dumps(chat)).replace('MID', str(mid)).replace('OTHER', json.dumps(other))
    path = temp/'src/shell.qml'
    source = path.read_text().replace('import QtQuick\n', 'import QtQuick\nimport QtTest\n', 1)
    source = source.replace('function pinLatest() {', 'function pinLatest() { testPinCalls++;', 1)
    path.write_text(source.rsplit('}', 1)[0]+code+'\n}\n')
    runtime = temp/'runtime'
    runtime.mkdir(mode=0o700)
    env = {**os.environ, 'XDG_RUNTIME_DIR': str(runtime), 'FEATHER_DATA_DIR': str(temp/'data'),
           'QT_QPA_PLATFORM': 'offscreen', 'QT_QPA_PLATFORMTHEME': 'generic',
           'QT_QUICK_CONTROLS_STYLE': 'Basic', 'QT_QUICK_BACKEND': 'software'}
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    result = subprocess.run(['qs', '-p', str(temp/'src'), '--no-color'], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=20)
    print(result.stdout)
    if result.returncode or 'SCROLL_SUCCESS' not in result.stdout or any(s in result.stdout for s in ('SCROLL_FAILURE', 'ReferenceError', 'TypeError', 'FAIL!')):
        raise SystemExit(1)
