import QtQuick

Rectangle {
    implicitWidth: 48
    implicitHeight: 48
    radius: width * 0.28
    color: Theme.selectedChat
    Image {
        anchors.fill: parent
        anchors.margins: parent.width * 0.12
        sourceSize: Qt.size(96, 96)
        source: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g fill="none" stroke="' + Theme.accent + '" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round"><path d="M17 44c-5-4-7-9-7-15 0-13 11-23 25-23s25 10 25 23S49 52 35 52H20L8 60l4-14"/><path d="M23 39c-4-11 4-22 19-23 1 14-6 24-19 23Zm-4 7 18-24m-9 14 9-1"/></g></svg>')
    }
}
