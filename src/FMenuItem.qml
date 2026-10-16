import QtQuick
import QtQuick.Controls.Basic

MenuItem {
    id: control
    implicitHeight: 34
    implicitWidth: 220
    padding: 10
    hoverEnabled: true
    contentItem: Text {
        text: control.text
        color: control.enabled ? Theme.fg : Theme.dim
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 5
        color: control.highlighted ? Theme.hover : "transparent"
        Behavior on color { enabled: Theme.effects; ColorAnimation { duration: 80 } }
    }
}
