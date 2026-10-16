import QtQuick

Rectangle {
    id: panel
    radius: 12
    color: Theme.popup
    border.color: Theme.border
    Rectangle {
        x: 0; y: 3
        width: panel.width; height: panel.height
        radius: panel.radius
        z: -1
        visible: Theme.effects
        color: "#000000"
        opacity: Theme.themeId === "paper" ? 0.09 : 0.18
    }
}
