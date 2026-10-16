import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root
    property string chatId: ""
    property string chatTitle: "New conversation"
    property string chatProject: ""
    property string selectedProject: ""
    property bool showArchived: false
    property bool chatArchived: false
    property int activeCount: 0
    property int archivedCount: 0
    property string actionChatId: ""
    property string actionChatTitle: ""
    property string actionChatProject: ""
    property bool actionChatArchived: false
    property var undoArchive: null
    property string selectedModel: ""
    property string accountLabel: ""
    property string activeAccount: ""
    property bool connected: false
    property bool planEnabled: false
    property bool busy: false
    property bool authBusy: false
    property bool ready: false
    property bool sidebarVisible: true
    property bool olderMessages: false
    property bool moreChats: false
    property int chatLimit: 60
    property bool pendingSend: false
    property string banner: ""
    property bool bannerError: false
    property var models: []
    property var projects: []
    property var accounts: []
    property string backgroundStyle: "none"
    property string backgroundImage: ""
    property string backgroundFit: "crop"
    property int backgroundStrength: 18
    property bool appearanceReady: false
    property bool appearanceSaving: false
    property var backgroundChoices: [
        {id:"none", name:"Solid color"}, {id:"contours", name:"Contours"},
        {id:"grid", name:"Graph paper"}, {id:"horizon", name:"Horizon"}, {id:"custom", name:"Your image"}
    ]
    readonly property string bg: Theme.bg
    readonly property string muted: Theme.muted
    readonly property string fg: Theme.fg
    readonly property string accent: Theme.accent

    Component.onCompleted: root.settings.watchFiles = false
    Connections { target: Quickshell; function onLastWindowClosed() { Qt.quit(); } }
    IpcHandler {
        target: "window"
        function show(): void {
            win.visible = true;
            if (surface.Window.window) surface.Window.window.requestActivate();
            composer.forceActiveFocus();
        }
    }

    ListModel { id: conversations }
    ListModel { id: messages }

    function call(value) {
        if (backend.running) backend.write(JSON.stringify(value) + "\n");
    }
    function saveAppearance() {
        appearanceSaving = true;
        call({op:"preferences", values:{theme:Theme.themeId, background:backgroundStyle,
             image:backgroundImage, fit:backgroundFit, strength:backgroundStrength, effects:Theme.effects}});
    }
    function applyAppearance(values) {
        Theme.themeId = values.theme;
        Theme.effects = values.effects;
        backgroundStyle = values.background;
        backgroundImage = values.image;
        backgroundFit = values.fit;
        backgroundStrength = values.strength;
        appearanceReady = true;
        appearanceSaving = false;
        for (let i=0;i<backgroundChoices.length;i++) if (backgroundChoices[i].id === values.background) backgroundPicker.currentIndex=i;
        fitPicker.currentIndex = values.fit === "fit" ? 1 : 0;
        strengthSlider.value = values.strength;
    }
    function notify(message, error) {
        undoArchive = null;
        banner = message;
        bannerError = !!error;
    }
    function refreshList() {
        call({op: "list", query: search.text, project: selectedProject, limit: chatLimit, archived: showArchived});
    }
    function projectName(id) {
        for (let p of projects) if (p.id === id) return p.name;
        return "Unfiled";
    }
    function openChatActions(id, title, folder, archived, anchor) {
        actionChatId = id; actionChatTitle = title;
        actionChatProject = folder; actionChatArchived = archived;
        chatMenu.popup(anchor, 0, anchor.height);
    }
    function setArchiveView(archived) {
        showArchived = archived;
        chatLimit = 60;
        refreshList();
    }
    function newChat() {
        if (busy) return;
        chatId = "";
        chatTitle = "New conversation";
        chatProject = selectedProject === "__unfiled__" ? "" : selectedProject;
        chatArchived = false;
        if (showArchived) setArchiveView(false);
        olderMessages = false;
        messages.clear();
        composer.text = "";
        composer.forceActiveFocus();
    }
    function send() {
        if (busy || pendingSend || chatArchived || !composer.text.trim()) return;
        if (!connected || !planEnabled) { settings.open(); return; }
        if (!selectedModel) { notify("Refresh the models in Account settings before sending.", true); return; }
        pendingSend = true;
        call({op:"send", chat:chatId, text:composer.text, model:selectedModel});
    }
    function bottom() { Qt.callLater(function() { transcript.positionViewAtEnd(); }); }
    function receive(e) {
        switch (e.event) {
        case "preferences": applyAppearance(e.values); break;
        case "ready": ready = true; break;
        case "account":
            connected = e.connected; planEnabled = e.plan_enabled;
            accountLabel = e.label; accounts = e.accounts; activeAccount = e.active;
            for (let i=0; i<accounts.length; i++) if (accounts[i].id === activeAccount) accountPicker.currentIndex=i;
            break;
        case "models":
            models = e.rows; selectedModel = e.selected;
            for (let i=0; i<models.length; i++) if (models[i].slug === e.selected) modelPicker.currentIndex = i;
            break;
        case "chats":
            conversations.clear();
            for (let row of e.rows) conversations.append({key:row.id, title:row.title, project:row.project_id || "", archived:!!row.archived});
            moreChats = e.more;
            if (e.counts) { activeCount = e.counts.active; archivedCount = e.counts.archived; }
            break;
        case "projects":
            projects = e.rows;
            Qt.callLater(function() {
                projectPicker.currentIndex = selectedProject === "__unfiled__" ? 1 : 0;
                for (let i=0; i<projects.length; i++) if (projects[i].id === selectedProject) projectPicker.currentIndex=i+2;
            });
            break;
        case "messages":
            if (e.prepend && e.chat !== chatId) break;
            let changedChat = chatId !== e.chat;
            chatId = e.chat; chatTitle = e.info.title; chatProject = e.info.project_id || "";
            chatArchived = !!e.info.archived;
            olderMessages = e.more;
            if (!e.prepend) messages.clear();
            for (let i=0; i<e.rows.length; i++) {
                let row = e.rows[i];
                let item = {key:row.id, role:row.role, content:row.content, status:row.status};
                if (e.prepend) messages.insert(i, item); else messages.append(item);
            }
            if (!e.prepend) { bottom(); if (changedChat && Theme.effects) chatReveal.restart(); }
            else Qt.callLater(function() { transcript.positionViewAtIndex(e.rows.length, ListView.Beginning); });
            break;
        case "busy":
            busy = e.busy;
            if (e.busy && pendingSend) { composer.text = ""; pendingSend = false; }
            break;
        case "delta":
            if (e.chat !== chatId) break;
            let follow = transcript.atYEnd;
            for (let i=messages.count-1; i>=0; i--) if (messages.get(i).key === e.id) {
                messages.setProperty(i,"content",messages.get(i).content+e.text); break;
            }
            if (follow) bottom();
            break;
        case "finished":
            if (e.chat === chatId) for (let i=messages.count-1; i>=0; i--) if (messages.get(i).key === e.id) {
                let follow = transcript.atYEnd;
                messages.setProperty(i,"status",e.status);
                if (follow) bottom();
                break;
            }
            break;
        case "auth_busy": authBusy = e.busy; break;
        case "notice": notify(e.message, false); break;
        case "error": pendingSend = false; appearanceSaving = false; notify(e.message, true); break;
        case "archived":
            if (chatId === e.chat) chatArchived = e.archived;
            notify(e.archived ? "Conversation archived." : "Conversation restored.", false);
            undoArchive = {chat:e.chat, archived:!e.archived};
            break;
        case "renamed": if (chatId === e.chat) chatTitle = e.title; break;
        case "moved":
            if (chatId === e.chat) chatProject = e.project;
            notify("Conversation moved to " + projectName(e.project) + ".", false);
            break;
        case "folder_deleted":
            if (selectedProject === e.id) { selectedProject = ""; projectPicker.currentIndex = 0; }
            if (chatProject === e.id) chatProject = "";
            break;
        case "deleted":
            if (chatId === e.chat) newChat();
            notify("Conversation deleted.", false);
            break;
        }
    }

    Process {
        id: backend
        command: ["python3", "-u", Qt.resolvedUrl("backend.py").toString().replace("file://", "")]
        running: true
        stdinEnabled: true
        onStarted: root.call({op:"init"})
        onExited: (code, status) => {
            root.ready = false;
            root.busy = false;
            root.pendingSend = false;
            root.notify("The chat service stopped. Close and reopen FeatherGPT to reconnect.", true);
        }
        stdout: SplitParser {
            onRead: line => {
                try { root.receive(JSON.parse(line)); }
                catch (error) { console.warn("Could not read a service event"); }
            }
        }
        stderr: SplitParser { onRead: line => console.warn("FeatherGPT service reported an error") }
    }

    FloatingWindow {
        id: win
        title: "FeatherGPT"
        implicitWidth: 1000
        implicitHeight: 700
        minimumSize: Qt.size(580, 440)
        color: root.bg

        Shortcut { sequence: "Ctrl+N"; onActivated: root.newChat() }
        Shortcut { sequence: "Ctrl+K"; onActivated: { root.sidebarVisible = true; search.forceActiveFocus(); } }
        Shortcut { sequence: "Ctrl+B"; onActivated: root.sidebarVisible = !root.sidebarVisible }
        Shortcut { sequence: "Ctrl+comma"; onActivated: settings.open() }
        Shortcut { sequence: "Ctrl+Shift+comma"; onActivated: appearance.open() }
        Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }
        Shortcut { sequence: "Escape"; enabled: root.busy; onActivated: root.call({op:"stop"}) }

        Item {
            id: surface
            anchors.fill: parent
            Rectangle { anchors.fill: parent; color: root.bg }
        RowLayout {
            anchors.fill: parent
            spacing: 0
            Rectangle {
                visible: root.sidebarVisible
                Layout.preferredWidth: win.width < 760 ? 204 : 240
                Layout.fillHeight: true
                color: Theme.sidebar
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 12
                    RowLayout {
                        Layout.fillWidth: true
                        Logo { Layout.preferredWidth: 30; Layout.preferredHeight: 30 }
                        Text { text: "FeatherGPT"; color: root.fg; font.pixelSize: 20; font.weight: Font.DemiBold; font.family: "sans-serif" }
                        Item { Layout.fillWidth: true }
                    }
                    FButton { id: newConversationButton; text: "+   New conversation"; primary: true; Layout.fillWidth: true; enabled: !root.busy; onClicked: root.newChat() }
                    FField {
                        id: search
                        Layout.fillWidth: true
                        placeholderText: "Search history…  Ctrl K"
                        onTextChanged: searchDelay.restart()
                        Timer { id: searchDelay; interval: 180; onTriggered: { root.chatLimit = 60; root.refreshList(); } }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "FOLDERS"; font.pixelSize: 10; font.letterSpacing: 1.5; color: root.muted }
                        Item { Layout.fillWidth: true }
                        FButton { text: "+"; subtle: true; implicitHeight: 26; onClicked: { projectDialog.editId = ""; projectTitle.text = ""; instructions.text = ""; projectDialog.open(); } }
                    }
                    ComboBox {
                        id: projectPicker
                        Layout.fillWidth: true
                        implicitHeight: 34
                        model: [{id:"", name:"All folders"},{id:"__unfiled__", name:"Unfiled"}].concat(root.projects)
                        textRole: "name"
                        font.pixelSize: 12
                        palette.text: root.fg
                        palette.buttonText: root.fg
                        palette.button: Theme.panel
                        palette.base: Theme.panel
                        palette.window: Theme.panel
                        palette.highlight: Theme.selection
                        onActivated: {
                            root.selectedProject = model[currentIndex].id;
                            root.chatLimit = 60;
                            root.refreshList();
                            if (!root.chatId) root.chatProject = root.selectedProject === "__unfiled__" ? "" : root.selectedProject;
                        }
                    }
                    FButton {
                        visible: root.selectedProject !== "" && root.selectedProject !== "__unfiled__"
                        text: "Edit folder"; subtle: true; Layout.fillWidth: true; implicitHeight: 28
                        onClicked: {
                            for (let p of root.projects) if (p.id === root.selectedProject) {
                                projectDialog.editId=p.id; projectTitle.text=p.name; instructions.text=p.instructions;
                                projectDialog.open(); break;
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        FButton { text: "Active · " + root.activeCount; Layout.fillWidth: true; primary: !root.showArchived; implicitHeight: 30; implicitWidth: 80; font.pixelSize: 11; onClicked: root.setArchiveView(false) }
                        FButton { text: "Archived · " + root.archivedCount; Layout.fillWidth: true; primary: root.showArchived; implicitHeight: 30; implicitWidth: 80; font.pixelSize: 11; onClicked: root.setArchiveView(true) }
                    }
                    Text { text: root.showArchived ? "ARCHIVED CONVERSATIONS" : "CONVERSATIONS"; font.pixelSize: 10; font.letterSpacing: 1.5; color: root.muted; topPadding: 8 }
                    ListView {
                        id: chatList
                        Layout.fillHeight: true
                        Layout.fillWidth: true
                        clip: true
                        reuseItems: true
                        cacheBuffer: 80
                        spacing: 3
                        model: conversations
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: ItemDelegate {
                            id: conversationRow
                            property alias actionButton: rowActions
                            required property string key
                            required property string title
                            required property string project
                            required property bool archived
                            required property int index
                            width: chatList.width
                            height: 38
                            enabled: !root.busy
                            hoverEnabled: true
                            rightPadding: 36
                            contentItem: Text { text: title; color: root.chatId === key ? root.accent : Theme.fg; font.pixelSize: 13; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                            background: Rectangle {
                                radius: 6
                                color: root.chatId === key ? Theme.selectedChat : conversationRow.hovered ? Theme.hover : "transparent"
                                Behavior on color { enabled: Theme.effects; ColorAnimation { duration: 100 } }
                            }
                            FButton {
                                id: rowActions
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                implicitWidth: 30; implicitHeight: 30; padding: 2
                                text: "···"; subtle: true
                                Accessible.name: "Actions for " + conversationRow.title
                                onClicked: root.openChatActions(key,title,project,archived,rowActions)
                            }
                            TapHandler { acceptedButtons: Qt.RightButton; onTapped: root.openChatActions(key,title,project,archived,conversationRow) }
                            onClicked: { composer.text = ""; root.call({op:"load",chat:key}); }
                        }
                        footer: FButton { visible: root.moreChats; width: chatList.width; text: "Load more"; subtle: true; onClicked: { root.chatLimit += 60; root.refreshList(); } }
                        Text { anchors.top: parent.top; anchors.topMargin: 10; width: parent.width; visible: conversations.count === 0; text: search.text ? "No matches found" : root.showArchived ? "No archived conversations in this folder." : "Your conversations will appear here."; color: Theme.dim; font.pixelSize: 12; wrapMode: Text.WordWrap }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    FButton { text: "Appearance"; subtle: true; Layout.fillWidth: true; onClicked: appearance.open() }
                    FButton {
                        text: root.connected ? "●   " + root.accountLabel : "○   Connect ChatGPT"
                        Layout.fillWidth: true
                        subtle: true
                        onClicked: settings.open()
                    }
                }
            }
            Rectangle { visible: root.sidebarVisible; Layout.fillHeight: true; implicitWidth: 1; color: Theme.border }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 12
                    spacing: 10
                    FButton { text: "☰"; subtle: true; onClicked: root.sidebarVisible = !root.sidebarVisible; ToolTip.visible: hovered; ToolTip.text: "Toggle sidebar · Ctrl B" }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Text { text: root.chatTitle; Layout.fillWidth: true; elide: Text.ElideRight; color: root.fg; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { text: (root.chatArchived ? "Archived · " : "") + (root.chatId || root.chatProject ? root.projectName(root.chatProject) : "Your local workspace"); color: root.muted; font.pixelSize: 11 }
                    }
                    ComboBox {
                        id: modelPicker
                        Layout.preferredWidth: Math.min(200,win.width*0.22)
                        implicitHeight: 34
                        model: root.models
                        textRole: "name"
                        displayText: root.models.length ? currentText : "Choose model"
                        enabled: !root.busy && root.models.length > 0
                        font.pixelSize: 12
                        palette.text: root.fg; palette.buttonText: root.fg; palette.button: Theme.panel; palette.base: Theme.panel; palette.window: Theme.panel; palette.highlight: Theme.selection
                        onActivated: { root.selectedModel=root.models[currentIndex].slug; root.call({op:"model",model:root.selectedModel}); }
                    }
                    FButton { id: headerActions; text: "···"; subtle: true; enabled: !!root.chatId && !root.busy; Accessible.name: "Conversation actions"; onClicked: root.openChatActions(root.chatId,root.chatTitle,root.chatProject,root.chatArchived,headerActions) }
                    Menu {
                        id: chatMenu
                        popupType: Popup.Item
                        enter: Transition { enabled: Theme.effects; NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 100 } }
                        exit: Transition { enabled: Theme.effects; NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 70 } }
                        palette.window: Theme.panel; palette.text: root.fg; palette.highlight: Theme.selection
                        FMenuItem { text: "Rename"; onTriggered: { renameField.text = root.actionChatTitle; renameDialog.open(); } }
                        FMenuItem { id: moveAction; text: "Move to folder…"; onTriggered: {
                            movePicker.currentIndex = 0;
                            for (let i=0;i<root.projects.length;i++) if (root.projects[i].id === root.actionChatProject) movePicker.currentIndex=i+1;
                            moveDialog.open();
                        } }
                        FMenuItem { id: archiveAction; text: root.actionChatArchived ? "Restore from archive" : "Archive conversation"; onTriggered: root.call({op:"archive",chat:root.actionChatId,archived:!root.actionChatArchived}) }
                        FMenuItem { text: "Export as Markdown"; onTriggered: root.call({op:"export",chat:root.actionChatId}) }
                        MenuSeparator {}
                        FMenuItem { id: deleteAction; text: "Delete conversation…"; onTriggered: deleteDialog.open() }
                    }
                }
                Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                Rectangle {
                    visible: root.banner !== ""
                    Layout.fillWidth: true
                    implicitHeight: noticeRow.implicitHeight + 20
                    color: root.bannerError ? Theme.errorBg : Theme.selectedChat
                    RowLayout {
                        id: noticeRow
                        anchors.fill: parent; anchors.margins: 10
                        Text { text: root.banner; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: root.bannerError ? Theme.errorText : root.accent; font.pixelSize: 12 }
                        FButton { visible: root.undoArchive !== null; text: "Undo"; subtle: true; enabled: !root.busy; onClicked: { let action=root.undoArchive; root.undoArchive=null; root.call({op:"archive",chat:action.chat,archived:action.archived}); } }
                        FButton { text: "×"; subtle: true; onClicked: { root.banner = ""; root.undoArchive = null; } }
                    }
                }
                Rectangle {
                    visible: root.chatArchived
                    Layout.fillWidth: true
                    implicitHeight: 48
                    color: Theme.selectedChat
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16
                        Text { text: "Archived · Restore to continue this conversation"; color: Theme.fg; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                        FButton { text: "Restore"; subtle: true; enabled: !root.busy; onClicked: root.call({op:"archive",chat:root.chatId,archived:false}) }
                    }
                }
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Backdrop {
                        id: chatBackdrop
                        anchors.fill: parent
                        style: root.backgroundStyle
                        customImage: root.backgroundImage
                        strength: root.backgroundStrength
                        fit: root.backgroundFit
                        onFailed: root.notify("This background image could not be displayed. Choose another image in Appearance.", true)
                    }
                    Column {
                        visible: messages.count === 0
                        anchors.centerIn: parent
                        width: Math.min(parent.width-50,480)
                        spacing: 16
                        Logo { width: 56; height: 56; anchors.horizontalCenter: parent.horizontalCenter }
                        Text { text: "What’s on your mind?"; color: root.fg; font.family: "sans-serif"; font.pixelSize: win.width < 760 ? 25 : 30; font.weight: Font.Medium; horizontalAlignment: Text.AlignHCenter; width: parent.width }
                        Text { text: "A quiet place to think, write, and work."; color: root.muted; font.pixelSize: 14; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap }
                        Item { width: 1; height: 6 }
                        FButton { visible: !root.connected; anchors.horizontalCenter: parent.horizontalCenter; text: "Continue with ChatGPT"; primary: true; onClicked: settings.open() }
                        Text { text: "Conversations and folders are saved on this laptop.\nExisting ChatGPT history stays in ChatGPT."; color: Theme.dim; font.pixelSize: 12; width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; lineHeight: 1.4 }
                    }
                    ListView {
                        id: transcript
                        SequentialAnimation {
                            id: chatReveal
                            PropertyAction { target: transcript; property: "opacity"; value: 0.65 }
                            NumberAnimation { target: transcript; property: "opacity"; to: 1; duration: 120; easing.type: Easing.OutQuad }
                        }
                        anchors.fill: parent
                        visible: messages.count > 0
                        clip: true
                        model: messages
                        reuseItems: true
                        cacheBuffer: 100
                        spacing: 20
                        topMargin: 24
                        bottomMargin: 24
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        header: Item {
                            width: transcript.width
                            height: root.olderMessages ? 52 : 0
                            FButton { visible: root.olderMessages; anchors.centerIn: parent; text: "Load earlier messages"; subtle: true; enabled: !root.busy; onClicked: root.call({op:"load",chat:root.chatId,before:messages.get(0).key}) }
                        }
                        delegate: Item {
                            id: messageDelegate
                            required property int key
                            required property string role
                            required property string content
                            required property string status
                            width: transcript.width
                            height: messageColumn.implicitHeight
                            Rectangle {
                                anchors.fill: messageColumn
                                anchors.margins: -10
                                visible: root.backgroundStyle !== "none"
                                color: Theme.bg
                                opacity: 0.94
                                radius: 8
                            }
                            Column {
                                id: messageColumn
                                width: Math.min(parent.width-48,760)
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 9
                                Row {
                                    spacing: 10
                                    Text { text: role === "user" ? "YOU" : "FEATHERGPT"; color: role === "user" ? root.muted : root.accent; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 1.4 }
                                    Text { text: status === "streaming" ? (content ? "" : "Thinking…") : status === "stopped" ? "Stopped" : status === "interrupted" ? "Interrupted" : ""; color: Theme.muted; font.pixelSize: 10 }
                                }
                                TextEdit {
                                    id: messageText
                                    width: parent.width
                                    text: content || (status === "streaming" ? " " : "No reply received.")
                                    textFormat: role === "assistant" && status === "complete" ? TextEdit.MarkdownText : TextEdit.PlainText
                                    readOnly: true
                                    selectByMouse: true
                                    persistentSelection: true
                                    wrapMode: TextEdit.Wrap
                                    color: root.fg
                                    selectionColor: Theme.selection
                                    selectedTextColor: Theme.fg
                                    font.family: "sans-serif"
                                    font.pixelSize: 14
                                    onLinkActivated: link => { if (/^https?:\/\//i.test(link)) Qt.openUrlExternally(link); }
                                }
                                FButton { text: "Copy"; visible: status !== "streaming"; subtle: true; implicitHeight: 25; onClicked: { messageText.selectAll(); messageText.copy(); messageText.deselect(); } }
                            }
                        }
                    }
                    FButton { visible: messages.count > 0 && !transcript.atYEnd; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 16; text: "↓ Latest"; onClicked: root.bottom() }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 20; Layout.rightMargin: 20; Layout.bottomMargin: 12
                    Layout.maximumWidth: 850
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 9
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: Math.min(160, Math.max(76, composer.contentHeight+36))
                        color: Theme.panel
                        radius: 12
                        border.color: composer.activeFocus ? Theme.strongBorder : Theme.border
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 12
                            spacing: 12
                            ScrollView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                                TextArea {
                                    id: composer
                                    placeholderText: root.chatArchived ? "Restore this conversation to reply" : root.busy ? "Reply in progress…" : "Message FeatherGPT…"
                                    placeholderTextColor: Theme.muted
                                    color: root.fg
                                    selectionColor: Theme.selection
                                    selectedTextColor: Theme.fg
                                    font.family: "sans-serif"
                                    font.pixelSize: 14
                                    wrapMode: TextEdit.Wrap
                                    padding: 3
                                    readOnly: root.busy || root.chatArchived
                                    cursorDelegate: Rectangle { width: 1; height: composer.cursorRectangle.height; color: root.accent; visible: composer.activeFocus && !root.busy && !root.chatArchived }
                                    background: null
                                    selectByMouse: true
                                    Keys.onReturnPressed: event => {
                                        if (!(event.modifiers & Qt.ShiftModifier)) { root.send(); event.accepted = true; }
                                        else event.accepted = false;
                                    }
                                    Keys.onEnterPressed: event => {
                                        if (!(event.modifiers & Qt.ShiftModifier)) { root.send(); event.accepted = true; }
                                        else event.accepted = false;
                                    }
                                }
                            }
                            FButton {
                                Layout.alignment: Qt.AlignBottom
                                text: root.busy ? "Stop" : "↑"
                                primary: !root.busy
                                enabled: root.ready && !root.authBusy && !root.chatArchived && (root.busy || composer.text.trim().length > 0)
                                onClicked: root.busy ? root.call({op:"stop"}) : root.send()
                                ToolTip.visible: hovered
                                ToolTip.text: root.busy ? "Stop reply · Esc" : "Send · Enter"
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Enter to send · Shift Enter for a new line"; color: Theme.dim; font.pixelSize: 10; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { text: root.busy ? "Streaming" : "Recent context · full history saved"; color: Theme.dim; font.pixelSize: 10 }
                    }
                }
            }
        }

        FPopup {
            id: settings
            parent: surface
            anchors.centerIn: parent
            width: Math.min(490, win.width-32)
            height: Math.min(settingsContent.implicitHeight+40,win.height-32)
            modal: true; focus: true; padding: 20
            background: FPanel {}
            ScrollView {
                anchors.fill: parent; clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    id: settingsContent
                    width: settings.availableWidth
                    spacing: 15
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Your account"; color: root.fg; font.pixelSize: 23; Layout.fillWidth: true }
                        FButton { text: "×"; subtle: true; onClicked: settings.close() }
                    }
                    Text { text: "Connect ChatGPT to use an eligible plan. Sign-in opens in your browser."; color: root.muted; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    ComboBox {
                        id: accountPicker
                        visible: root.accounts.length > 0
                        Layout.fillWidth: true
                        model: root.accounts; textRole: "label"
                        palette.text: root.fg; palette.buttonText: root.fg; palette.button: Theme.panel; palette.base: Theme.panel; palette.window: Theme.panel; palette.highlight: Theme.selection
                        enabled: !root.busy && !root.authBusy
                        onActivated: root.call({op:"switch",id:root.accounts[currentIndex].id})
                        Component.onCompleted: { for (let i=0;i<root.accounts.length;i++) if (root.accounts[i].id === root.activeAccount) currentIndex=i; }
                    }
                    Text { visible: root.connected; text: root.accountLabel + (root.planEnabled ? "\nChatGPT plan access enabled" : "\nChatGPT plan access has not been granted"); color: root.accent; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    FButton {
                        text: root.authBusy ? "Waiting for browser…" : "Continue with ChatGPT"
                        primary: true; Layout.fillWidth: true; enabled: !root.authBusy && !root.busy
                        onClicked: { root.banner=""; root.call({op:"login"}); }
                    }
                    Text { visible: root.authBusy; text: "Finish signing in in your browser, then return here."; color: root.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    Text { visible: root.bannerError && root.banner !== ""; text: root.banner; color: Theme.errorText; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    FButton { visible: root.authBusy; text: "Cancel sign-in"; Layout.fillWidth: true; onClicked: root.call({op:"cancel_login"}) }
                    RowLayout {
                        visible: !root.authBusy
                        Layout.fillWidth: true
                        FButton { text: "Add account"; enabled: !root.busy; onClicked: root.call({op:"login",new:true}) }
                        FButton { text: "Refresh models"; enabled: root.connected && !root.busy; onClicked: root.call({op:"models"}) }
                        FButton { text: "Sign out"; enabled: root.connected && !root.busy; onClicked: root.call({op:"signout"}) }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.border }
                    Text { text: "Made for a lighter desktop"; color: root.fg; font.pixelSize: 14; font.weight: Font.DemiBold }
                    Text { text: "Native interface. No embedded browser. No background polling.\n\nHistory and folders live on this laptop and do not sync with ChatGPT. Only recent completed messages and folder instructions are sent for context.\n\nFeatherGPT is an independent client, not an official OpenAI app."; color: root.muted; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    FButton { text: "Manage ChatGPT usage and app access ↗"; subtle: true; Layout.fillWidth: true; onClicked: Qt.openUrlExternally("https://chatgpt.com/#settings") }
                }
            }
        }

        FileDialog {
            id: imagePicker
            title: "Choose a FeatherGPT background"
            nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.svg)"]
            fileMode: FileDialog.OpenFile
            onAccepted: root.call({op:"preferences",values:{background:"custom",image:selectedFile.toString()}})
        }
        FPopup {
            id: appearance
            parent: surface
            anchors.centerIn: parent
            width: Math.min(490,win.width-32)
            height: Math.min(615,win.height-32)
            modal: true; focus: true; padding: 20
            background: FPanel {}
            ScrollView {
                anchors.fill: parent; clip: true
                contentWidth: availableWidth
                ColumnLayout {
                    width: appearance.availableWidth
                    spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Logo { Layout.preferredWidth: 35; Layout.preferredHeight: 35 }
                        Text { text: "Make it yours"; color: Theme.fg; font.pixelSize: 23; Layout.fillWidth: true }
                        FButton { text: "×"; subtle: true; onClicked: appearance.close() }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "Gentle effects"; color: Theme.fg; font.pixelSize: 14 }
                            Text { text: "Quick fades, button feedback and soft edges"; color: Theme.muted; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                        }
                        Switch {
                            id: effectsSwitch
                            checked: Theme.effects
                            Accessible.name: "Gentle effects"
                            implicitWidth: 48; implicitHeight: 28; padding: 2
                            indicator: Rectangle {
                                x: effectsSwitch.leftPadding
                                y: effectsSwitch.topPadding + (effectsSwitch.availableHeight - height) / 2
                                implicitWidth: 44; implicitHeight: 24
                                radius: 12
                                color: effectsSwitch.checked ? Theme.accent : Theme.border
                                border.width: effectsSwitch.visualFocus ? 2 : 0
                                border.color: Theme.fg
                                Behavior on color { enabled: Theme.effects; ColorAnimation { duration: 90 } }
                                Rectangle {
                                    x: effectsSwitch.checked ? parent.width - width - 3 : 3
                                    y: 3; width: 18; height: 18; radius: 9
                                    color: Theme.popup
                                    Behavior on x { enabled: Theme.effects; NumberAnimation { duration: 90 } }
                                }
                            }
                            onToggled: { Theme.effects=checked; root.saveAppearance(); }
                        }
                    }
                    Text { text: "THEME"; color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    GridLayout {
                        columns: 2
                        Layout.fillWidth: true
                        columnSpacing: 12; rowSpacing: 12
                        Repeater {
                            model: Theme.choices
                            delegate: Button {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 77
                                hoverEnabled: true
                                padding: 12
                                Accessible.name: modelData.name + " theme"
                                background: Rectangle {
                                    color: modelData.bg; radius: 9
                                    border.width: Theme.themeId === modelData.id ? 2 : 1
                                    border.color: Theme.themeId === modelData.id ? Theme.accent : modelData.border
                                }
                                contentItem: ColumnLayout {
                                    spacing: 9
                                    Row {
                                        spacing: 5
                                        Repeater {
                                            model: [modelData.accent,modelData.muted,modelData.panel]
                                            Rectangle { required property var modelData; width: 22; height: 10; radius: 3; color: modelData }
                                        }
                                    }
                                    Text { text: modelData.name + (Theme.themeId === modelData.id ? "  ✓" : ""); color: modelData.fg; font.pixelSize: 13; font.weight: Font.Medium }
                                }
                                onClicked: { Theme.themeId=modelData.id; root.saveAppearance(); }
                            }
                        }
                    }
                    Text { text: "BACKGROUND"; color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    ComboBox {
                        id: backgroundPicker
                        Layout.fillWidth: true
                        model: root.backgroundChoices; textRole: "name"
                        palette.text: Theme.fg; palette.buttonText: Theme.fg; palette.button: Theme.panel; palette.base: Theme.panel; palette.window: Theme.panel; palette.highlight: Theme.selection
                        onActivated: {
                            if (model[currentIndex].id === "custom" && !root.backgroundImage) imagePicker.open();
                            else { root.backgroundStyle=model[currentIndex].id; root.saveAppearance(); }
                        }
                    }
                    RowLayout {
                        visible: root.backgroundStyle === "custom" || backgroundPicker.currentIndex === 4
                        Layout.fillWidth: true
                        Text { text: root.backgroundImage ? decodeURIComponent(root.backgroundImage.split("/").pop()) : "No image selected"; color: Theme.muted; font.pixelSize: 12; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        FButton { text: "Choose image…"; onClicked: imagePicker.open() }
                    }
                    RowLayout {
                        visible: root.backgroundStyle === "custom"
                        Layout.fillWidth: true
                        Text { text: "Image fit"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                        ComboBox {
                            id: fitPicker
                            Layout.preferredWidth: 160
                            model: ["Fill the space", "Show whole image"]
                            palette.text: Theme.fg; palette.buttonText: Theme.fg; palette.button: Theme.panel; palette.base: Theme.panel; palette.window: Theme.panel; palette.highlight: Theme.selection
                            onActivated: { root.backgroundFit=currentIndex === 1 ? "fit" : "crop"; root.saveAppearance(); }
                        }
                    }
                    ColumnLayout {
                        visible: root.backgroundStyle !== "none"
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "Background strength"; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
                            Text { text: root.backgroundStrength + "%"; color: Theme.accent; font.pixelSize: 12 }
                        }
                        Slider {
                            id: strengthSlider
                            Layout.fillWidth: true
                            from: 0; to: 35; stepSize: 1
                            value: root.backgroundStrength
                            background: Rectangle {
                                x: strengthSlider.leftPadding
                                y: strengthSlider.topPadding + strengthSlider.availableHeight / 2 - height / 2
                                implicitHeight: 4; height: 4; radius: 2
                                width: strengthSlider.availableWidth
                                color: Theme.border
                                Rectangle { width: parent.width * strengthSlider.visualPosition; height: parent.height; radius: 2; color: Theme.accent }
                            }
                            handle: Rectangle {
                                x: strengthSlider.leftPadding + strengthSlider.visualPosition * (strengthSlider.availableWidth - width)
                                y: strengthSlider.topPadding + strengthSlider.availableHeight / 2 - height / 2
                                width: 18; height: 18; radius: 9
                                color: Theme.accent
                                border.width: strengthSlider.visualFocus ? 2 : 0
                                border.color: Theme.fg
                            }
                            onMoved: { root.backgroundStrength=Math.round(value); strengthSave.restart(); }
                            Timer { id: strengthSave; interval: 200; onTriggered: root.saveAppearance() }
                        }
                    }
                    Text { text: "Static backgrounds keep things quiet. Your image stays on this laptop; it is never sent with messages."; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Text { visible: root.bannerError && root.banner !== ""; text: root.banner; color: Theme.errorText; font.pixelSize: 12; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: root.appearanceSaving ? "Saving…" : "Saved on this laptop"; color: Theme.dim; font.pixelSize: 11; Layout.fillWidth: true }
                        FButton { text: "Reset appearance"; subtle: true; onClicked: root.call({op:"preferences",reset:true}) }
                    }
                }
            }
        }

        FPopup {
            id: projectDialog
            property string editId: ""
            parent: surface; anchors.centerIn: parent
            width: Math.min(480,win.width-32); height: Math.min(415,win.height-32)
            padding: 20; modal: true; focus: true
            background: FPanel {}
            ColumnLayout {
                anchors.fill: parent; spacing: 14
                Text { text: projectDialog.editId ? "Edit folder" : "New folder"; color: root.fg; font.pixelSize: 22 }
                FField { id: projectTitle; placeholderText: "Folder name"; Layout.fillWidth: true; maximumLength: 80 }
                Text { text: "Optional instructions for conversations in this folder"; color: root.muted; font.pixelSize: 12 }
                ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    TextArea { id: instructions; placeholderText: "What should FeatherGPT know about this folder?"; wrapMode: TextEdit.Wrap; color: root.fg; placeholderTextColor: Theme.muted; font.pixelSize: 13; padding: 10; background: Rectangle { color: Theme.field; radius: 7; border.color: Theme.border } }
                }
                RowLayout {
                    FButton { id: removeFolderButton; text: "Remove folder…"; visible: !!projectDialog.editId; subtle: true; enabled: !root.busy; onClicked: { folderDeleteDialog.folderId=projectDialog.editId; folderDeleteDialog.folderName=projectTitle.text; projectDialog.close(); folderDeleteDialog.open(); } }
                    Item { Layout.fillWidth: true }
                    FButton { text: "Cancel"; subtle: true; onClicked: projectDialog.close() }
                    FButton { text: "Save folder"; primary: true; enabled: projectTitle.text.trim().length>0; onClicked: { root.call({op:"project",id:projectDialog.editId,name:projectTitle.text,instructions:instructions.text}); projectDialog.close(); } }
                }
            }
        }
        FPopup {
            id: renameDialog
            parent: surface; anchors.centerIn: parent; width: Math.min(420,win.width-32); height: 165
            padding: 20; modal: true; focus: true
            background: FPanel {}
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                Text { text: "Rename conversation"; color: root.fg; font.pixelSize: 19 }
                FField { id: renameField; Layout.fillWidth: true; maximumLength: 100; onAccepted: { if (text.trim()) { root.call({op:"rename",chat:root.actionChatId,title:text}); renameDialog.close(); } } }
                FButton { text: "Save"; primary: true; Layout.alignment: Qt.AlignRight; enabled: renameField.text.trim().length>0; onClicked: { root.call({op:"rename",chat:root.actionChatId,title:renameField.text}); renameDialog.close(); } }
            }
        }
        FPopup {
            id: moveDialog
            parent: surface; anchors.centerIn: parent; width: Math.min(420,win.width-32); height: 180
            padding: 20; modal: true; focus: true
            background: FPanel {}
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                Text { text: "Move conversation"; color: root.fg; font.pixelSize: 19 }
                ComboBox { id: movePicker; Layout.fillWidth: true; model: [{id:"",name:"Unfiled"}].concat(root.projects); textRole: "name"; palette.text: root.fg; palette.buttonText: root.fg; palette.button: Theme.panel; palette.base: Theme.panel; palette.window: Theme.panel; palette.highlight: Theme.selection }
                FButton { id: confirmMoveButton; text: "Move"; primary: true; Layout.alignment: Qt.AlignRight; onClicked: { root.call({op:"move",chat:root.actionChatId,project:movePicker.model[movePicker.currentIndex].id}); moveDialog.close(); } }
            }
        }
        FPopup {
            id: deleteDialog
            parent: surface; anchors.centerIn: parent; width: Math.min(440,win.width-32); height: 195
            padding: 20; modal: true; focus: true
            background: FPanel {}
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                Text { text: "Delete this conversation?"; color: root.fg; font.pixelSize: 19 }
                Text { text: root.actionChatTitle; color: Theme.muted; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { text: "This permanently removes its messages from this laptop."; color: root.muted; font.pixelSize: 12 }
                RowLayout { Layout.alignment: Qt.AlignRight; FButton { id: cancelDeleteButton; text: "Cancel"; onClicked: deleteDialog.close() } FButton { id: confirmDeleteButton; text: "Delete"; onClicked: { root.call({op:"delete",chat:root.actionChatId}); deleteDialog.close(); } } }
            }
        }
        FPopup {
            id: folderDeleteDialog
            property string folderId: ""
            property string folderName: ""
            parent: surface; anchors.centerIn: parent
            width: Math.min(440,win.width-32); height: 210
            padding: 20; modal: true; focus: true
            ColumnLayout {
                anchors.fill: parent; spacing: 12
                Text { text: "Remove this folder?"; color: Theme.fg; font.pixelSize: 20 }
                Text { text: folderDeleteDialog.folderName; color: Theme.muted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                Text { text: "Its conversations will move to Unfiled. No conversations or messages will be deleted."; color: Theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                RowLayout {
                    Layout.alignment: Qt.AlignRight
                    FButton { text: "Cancel"; onClicked: folderDeleteDialog.close() }
                    FButton { id: confirmFolderDeleteButton; text: "Remove folder"; onClicked: { root.call({op:"delete_project",id:folderDeleteDialog.folderId}); folderDeleteDialog.close(); } }
                }
            }
        }
        } // surface
        Component.onCompleted: composer.forceActiveFocus()
    }
}
