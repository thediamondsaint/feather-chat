import QtQuick

Item {
    id: backdrop
    property string style: "none"
    property url customImage: ""
    property string fit: "crop"
    property int strength: 18
    readonly property int imageStatus: artwork.status
    signal failed()
    clip: true
    Rectangle { anchors.fill: parent; color: Theme.bg; Behavior on color { enabled: Theme.effects; ColorAnimation { duration: 140 } } }
    Rectangle {
        anchors.fill: parent
        visible: backdrop.style === "horizon"
        opacity: backdrop.strength / 100
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.bg }
            GradientStop { position: 0.68; color: Theme.accent }
            GradientStop { position: 1; color: Theme.bg }
        }
    }
    Image {
        id: artwork
        anchors.fill: parent
        visible: source.toString() !== ""
        source: backdrop.style === "custom" ? backdrop.customImage
              : backdrop.style === "contours" || backdrop.style === "grid" ? Qt.resolvedUrl("assets/backgrounds/" + backdrop.style + ".svg") : ""
        sourceSize: backdrop.style === "custom" ? Qt.size(1600, 1000) : Qt.size(640, 480)
        asynchronous: true
        cache: false
        autoTransform: true
        smooth: backdrop.style === "custom"
        opacity: backdrop.strength / 100
        fillMode: backdrop.style !== "custom" ? Image.Tile : backdrop.fit === "fit" ? Image.PreserveAspectFit : Image.PreserveAspectCrop
        onStatusChanged: if (status === Image.Error) backdrop.failed()
    }
}
