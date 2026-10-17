#!/usr/bin/env python3
"""Run real Quickshell offscreen, exercise stdio/UI, and save visual previews."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

project=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project/'src'))
from backend import Store

with tempfile.TemporaryDirectory(prefix='feather-ui-') as tmp:
    temp=Path(tmp)
    shutil.copytree(project/'src',temp/'src',ignore=shutil.ignore_patterns('__pycache__'))
    custom=temp/'my background.svg'
    shutil.copy2(project/'src/assets/backgrounds/contours.svg',custom)
    store=Store(temp/'data')
    chat=store.chat()
    store.write('UPDATE chats SET title=? WHERE id=?',('A lighter Linux desktop',chat))
    for role,content in [('user','How can I make this laptop feel faster?'),('assistant','## Keep it simple\n\nA few small changes make a useful difference:\n\n- Keep only the apps you need open.\n- Prefer native tools for everyday work.\n- Load long histories in small batches.\n\n```bash\nfree -m\n```\n\nYour conversations are saved locally, so you can pick up where you left off.')]:
        store.write('INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)',(chat,role,content))
    store.db.close()
    # Saved signed-out registrations exercise real switching without networking.
    (temp/'data/accounts.json').write_text(json.dumps(dict(active='profile-a', host='test-host', accounts={
        'profile-a': dict(client_id='profile-a', email='personal@example.test'),
        'profile-b': dict(client_id='profile-b', email='work@example.test'),
    })))
    previews=Path(os.environ.get('FEATHER_PREVIEW_DIR') or project/'previews')
    previews.mkdir(parents=True,exist_ok=True)
    snippet='''
    Timer {
        property int stage: 0
        property int ticks: 0
        property bool capturing: false
        interval: 120; running: true; repeat: true
        function check(condition, message) { if (!condition) { console.error("TEST_FAILURE " + message); Qt.quit(); } }
        function capture(name) { capturing=true; surface.grabToImage(function(result) { result.saveToFile(PREVIEW + "/" + name + ".png"); capturing=false; stage++; }); }
        onTriggered: {
            if (capturing) return;
            ticks++;
            if (ticks > 180) { console.error("TEST_FAILURE timeout"); Qt.quit(); return; }
            if (stage === 0 && root.ready) {
                check(conversations.count === 1,"history did not load");
                capture("welcome");
            } else if (stage === 1) {
                root.call({op:"project", id:"p",name:"My workspace",instructions:"Keep answers concise."}); stage++;
            } else if (stage === 2 && root.projects.length === 1) {
                root.banner="";
                root.call({op:"load",chat:CHAT}); stage++;
            } else if (stage === 3 && messages.count === 2) {
                check(root.chatTitle === "A lighter Linux desktop", "conversation title");
                root.receive({event:"models",rows:[{slug:"test",name:"Test model"}],selected:"test"});
                stage++;
            } else if (stage === 4) {
                capture("conversation");
            } else if (stage === 5) {
                messages.append({key:999,role:"assistant",content:"",status:"streaming"});
                root.receive({event:"delta",chat:CHAT,id:999,text:"Streamed reply"});
                root.receive({event:"finished",chat:CHAT,id:999,status:"complete"});
                check(messages.get(2).content === "Streamed reply", "stream update");
                check(messages.get(2).status === "complete", "completion status");
                root.newChat();
                check(messages.count === 0 && root.chatId === "", "new conversation");
                composer.text = "Draft survives a rejected send";
                root.send();
                check(composer.text === "Draft survives a rejected send", "draft was lost");
                settings.close(); search.text = "no-such-phrase"; stage++;
            } else if (stage === 6 && conversations.count === 0) {
                search.text = ""; stage++;
            } else if (stage === 7 && conversations.count === 1) {
                surface.Overlay.overlay.parent=surface;
                settings.open(); stage++;
            } else if (stage === 8) {
                capture("account");
            } else if (stage === 9) {
                settings.close(); composer.text="";
                surface.Window.window.width=600; surface.Window.window.height=480; stage++;
            } else if (stage === 10) {
                capture("compact");
            } else if (stage === 11) {
                surface.Window.window.width=1000; surface.Window.window.height=700;
                check(root.appearanceReady,"preferences did not initialize");
                Theme.themeId="midnight"; root.backgroundStyle="contours"; root.saveAppearance(); stage++;
            } else if (stage === 12 && !root.appearanceSaving && chatBackdrop.imageStatus === Image.Ready) {
                capture("theme-midnight");
            } else if (stage === 13) {
                Theme.themeId="paper"; root.backgroundStyle="grid"; root.saveAppearance(); stage++;
            } else if (stage === 14 && !root.appearanceSaving && chatBackdrop.imageStatus === Image.Ready) {
                check(Theme.accentText.toString() === "#ffffff", "Paper theme button text contrast");
                capture("theme-paper");
            } else if (stage === 15) {
                Theme.themeId="plum"; root.backgroundStyle="horizon"; root.saveAppearance(); stage++;
            } else if (stage === 16 && !root.appearanceSaving) {
                capture("theme-plum");
            } else if (stage === 17) {
                appearance.open(); stage++;
            } else if (stage === 18) {
                capture("appearance");
            } else if (stage === 19) {
                appearance.close();
                imagePicker.selectedFile=CUSTOM;
                imagePicker.accepted(); stage++;
            } else if (stage === 20 && root.backgroundStyle === "custom" && chatBackdrop.imageStatus === Image.Ready) {
                check(root.backgroundImage.indexOf("%20") !== -1,"image filename was not encoded");
                capture("custom-background");
            } else if (stage === 21) {
                root.call({op:"preferences",reset:true}); stage++;
            } else if (stage === 22 && Theme.themeId === "forest" && root.backgroundStyle === "none") {
                root.call({op:"load",chat:CHAT}); stage++;
            } else if (stage === 23 && root.chatId === CHAT && messages.count === 2) {
                check(Theme.effects,"effects must default to enabled");
                let row=chatList.itemAtIndex(0);
                check(row !== null,"conversation row missing");
                check(row.actionButton.contentItem.width >= row.actionButton.contentItem.implicitWidth,"row action label is clipped");
                row.actionButton.clicked(); stage++;
            } else if (stage === 24) {
                check(root.actionChatId === CHAT,"row action targets wrong conversation");
                capture("conversation-actions");
            } else if (stage === 25) {
                archiveAction.triggered(); chatMenu.close(); stage++;
            } else if (stage === 26 && root.chatArchived && root.archivedCount === 1) {
                check(composer.readOnly,"archived composer should be read-only");
                check(root.undoArchive !== null,"archive undo is missing");
                root.setArchiveView(true); stage++;
            } else if (stage === 27 && conversations.count === 1 && conversations.get(0).archived) {
                check(root.activeCount === 0,"archived chat remained active");
                capture("archive-view");
            } else if (stage === 28) {
                root.openChatActions(root.chatId,root.chatTitle,root.chatProject,true,headerActions);
                archiveAction.triggered(); chatMenu.close(); stage++;
            } else if (stage === 29 && !root.chatArchived && root.archivedCount === 0) {
                root.setArchiveView(false);
                root.openChatActions(root.chatId,root.chatTitle,root.chatProject,false,headerActions);
                moveAction.triggered(); chatMenu.close(); stage++;
            } else if (stage === 30) {
                movePicker.currentIndex=1; confirmMoveButton.clicked(); stage++;
            } else if (stage === 31 && root.chatProject === "p") {
                root.selectedProject="p"; root.refreshList(); stage++;
            } else if (stage === 32 && conversations.count === 1 && projectPicker.currentIndex === 2) {
                capture("folder-view");
            } else if (stage === 33) {
                projectDialog.editId="p"; projectTitle.text="My workspace";
                projectDialog.open(); stage++;
            } else if (stage === 34) {
                removeFolderButton.clicked(); stage++;
            } else if (stage === 35) {
                check(folderDeleteDialog.visible,"folder removal confirmation missing");
                confirmFolderDeleteButton.clicked(); stage++;
            } else if (stage === 36 && root.projects.length === 0 && root.selectedProject === "") {
                check(root.chatId === CHAT && messages.count === 2,"folder removal lost the conversation");
                check(root.chatProject === "","removed folder still assigned");
                root.selectedProject="__unfiled__"; root.refreshList(); stage++;
            } else if (stage === 37 && conversations.count === 1 && projectPicker.currentIndex === 1) {
                root.openChatActions(root.chatId,root.chatTitle,root.chatProject,false,headerActions);
                deleteAction.triggered(); chatMenu.close(); stage++;
            } else if (stage === 38) {
                check(deleteDialog.visible,"conversation deletion confirmation missing");
                cancelDeleteButton.clicked(); stage++;
            } else if (stage === 39) {
                check(messages.count === 2 && root.chatId === CHAT,"cancel deleted the conversation");
                deleteDialog.open(); stage++;
            } else if (stage === 40) {
                confirmDeleteButton.clicked(); stage++;
            } else if (stage === 41 && root.chatId === "" && conversations.count === 0) {
                appearance.open(); stage++;
            } else if (stage === 42) {
                effectsSwitch.checked=false; effectsSwitch.toggled(); stage++;
            } else if (stage === 43 && !root.appearanceSaving) {
                check(!Theme.effects,"effects toggle did not apply");
                appearance.close(); stage++;
            } else if (stage === 44) {
                appearance.open(); stage++;
            } else if (stage === 45) {
                check(appearance.opacity === 1,"popup faded out with reduced effects");
                check(!chatReveal.running,"chat fade did not stop");
                appearance.close();
                composer.text="Keep this draft";
                profileButton.clicked(); stage++;
            } else if (stage === 46) {
                check(profiles.visible,"profile picker did not open");
                check(profileRepeater.count === 2,"saved profiles missing");
                capture("profiles");
            } else if (stage === 47) {
                profileRepeater.itemAt(1).clicked();
                check(root.profileSwitchPending,"switch should guard sending until backend confirms");
                stage++;
            } else if (stage === 48 && root.activeAccount === "profile-b" && !root.profileSwitchPending) {
                check(composer.text === "Keep this draft","profile switch lost draft");
                check(root.models.length === 0 && root.selectedModel === "","signed-out profile retained models");
                check(accountPicker.currentIndex === 1,"settings picker out of sync");
                root.cycleProfile(-1); stage++;
            } else if (stage === 49 && root.activeAccount === "profile-a" && !root.profileSwitchPending) {
                check(accountPicker.currentIndex === 0,"reverse switch out of sync");
                root.pendingSend=true; root.cycleProfile(1);
                check(!root.profileSwitchPending,"switched while a send was pending");
                root.pendingSend=false;
                console.log("TEST_SUCCESS profile picker, account switching, draft preservation, guards, history, themes, backgrounds, row menus, archive, restore, folders, unfiled, safe folder removal, confirmed delete, cancel delete, reduced effects");
                Qt.quit();
            }
        }
    }
'''.replace('PREVIEW',json.dumps(str(previews))).replace('CHAT',json.dumps(chat)).replace('CUSTOM',json.dumps(custom.as_uri()))
    path=temp/'src/shell.qml'
    source=path.read_text(); path.write_text(source.rsplit('}',1)[0]+snippet+'\n}\n')
    runtime=temp/'runtime'; runtime.mkdir(mode=0o700)
    env={**os.environ,'XDG_RUNTIME_DIR':str(runtime),'FEATHER_DATA_DIR':str(temp/'data'),'QT_QPA_PLATFORM':'offscreen','QT_QPA_PLATFORMTHEME':'generic','QT_QUICK_CONTROLS_STYLE':'Basic','QT_QUICK_BACKEND':'software'}
    env.pop('DISPLAY',None); env.pop('WAYLAND_DISPLAY',None)
    result=subprocess.run(['qs','-p',str(temp/'src'),'--no-color'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
    print(result.stdout)
    if result.returncode or 'TEST_SUCCESS' not in result.stdout or 'TEST_FAILURE' in result.stdout or 'ReferenceError' in result.stdout or 'TypeError' in result.stdout:
        raise SystemExit(1)
    saved=json.loads((temp/'data/preferences.json').read_text())
    assert saved['theme']=='forest' and saved['background']=='none' and saved['effects'] is False
    db=Store(temp/'data')
    assert db.rows('SELECT * FROM chats') == []
    assert db.rows('SELECT * FROM messages') == []
    assert db.rows('SELECT * FROM search') == []
    db.db.close()
    print('Previews:',previews)
