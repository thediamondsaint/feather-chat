import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: control
    implicitHeight: 38
    leftPadding: 12
    rightPadding: 12
    color: Theme.fg
    placeholderTextColor: Theme.muted
    selectionColor: Theme.selection
    selectedTextColor: Theme.fg
    font.family: "sans-serif"
    font.pixelSize: 13
    background: Rectangle {
        color: Theme.field
        radius: 7
        border.color: control.activeFocus ? Theme.strongBorder : Theme.border
    }
}
