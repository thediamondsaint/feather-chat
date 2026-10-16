import QtQuick
import QtQuick.Controls.Basic

Button {
    id: control
    property bool primary: false
    property bool subtle: false
    implicitHeight: 36
    implicitWidth: Math.max(36, label.implicitWidth + 24)
    hoverEnabled: true
    padding: 10
    font.family: "sans-serif"
    font.pixelSize: 13
    contentItem: Text {
        id: label
        text: control.text
        color: !control.enabled ? Theme.dim : control.primary ? Theme.accentText : Theme.fg
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 7
        color: control.primary ? (control.down ? Theme.accentPressed : Theme.accent) : control.down ? Theme.pressed : control.hovered ? Theme.hover : control.subtle ? "transparent" : Theme.panel
        border.width: control.visualFocus ? 2 : control.subtle || control.primary ? 0 : 1
        border.color: control.visualFocus ? Theme.accent : Theme.border
    }
}
