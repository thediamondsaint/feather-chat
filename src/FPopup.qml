import QtQuick
import QtQuick.Controls.Basic

Popup {
    popupType: Popup.Item
    enter: Transition {
        enabled: Theme.effects
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120; easing.type: Easing.OutQuad }
            NumberAnimation { property: "scale"; from: 0.985; to: 1; duration: 120; easing.type: Easing.OutQuad }
        }
    }
    exit: Transition {
        enabled: Theme.effects
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 80 }
    }
    background: FPanel {}
}
