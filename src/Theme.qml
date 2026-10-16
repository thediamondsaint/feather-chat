pragma Singleton
import QtQuick

QtObject {
    property bool effects: true
    property string themeId: "forest"
    readonly property var choices: [
        { id: "forest", name: "Forest", bg: "#191e1b", sidebar: "#141916", panel: "#222b25", field: "#191f1b", border: "#354039", strongBorder: "#6d957b", fg: "#e5ece6", muted: "#95a298", dim: "#7e9083", accent: "#a4d6b6", accentText: "#14251e", accentPressed: "#79b493", hover: "#2c3530", pressed: "#354139", selection: "#476952", selectedChat: "#26362c", popup: "#1d2620", errorBg: "#392720", errorText: "#f4c5ae" },
        { id: "midnight", name: "Midnight", bg: "#131a27", sidebar: "#0f1520", panel: "#1c2738", field: "#151e2d", border: "#30435b", strongBorder: "#668eb5", fg: "#e5edf7", muted: "#9bacc2", dim: "#8196b0", accent: "#97c9f5", accentText: "#10263b", accentPressed: "#70aad9", hover: "#26364d", pressed: "#30425c", selection: "#3b608b", selectedChat: "#213751", popup: "#1a2638", errorBg: "#3b2830", errorText: "#f4bab3" },
        { id: "plum", name: "Plum", bg: "#211a28", sidebar: "#19141f", panel: "#2d2335", field: "#241c2c", border: "#493650", strongBorder: "#a17baa", fg: "#f1e7f4", muted: "#b5a0be", dim: "#a28bac", accent: "#d4ade4", accentText: "#302037", accentPressed: "#b98bc9", hover: "#3c2e45", pressed: "#493650", selection: "#775183", selectedChat: "#3d2d48", popup: "#2b2133", errorBg: "#432c30", errorText: "#f6c0b4" },
        { id: "paper", name: "Paper", bg: "#f6f3eb", sidebar: "#eae7dd", panel: "#fffdf7", field: "#f7f4ed", border: "#d0ccbf", strongBorder: "#648473", fg: "#25382d", muted: "#5d6c60", dim: "#6b766a", accent: "#315f49", accentText: "#ffffff", accentPressed: "#244c38", hover: "#dedfd3", pressed: "#ccd3c5", selection: "#bdd8c4", selectedChat: "#d5e3d4", popup: "#fffdf7", errorBg: "#f7e1d5", errorText: "#8a3928" }
    ]
    readonly property var colors: {
        for (let theme of choices) if (theme.id === themeId) return theme;
        return choices[0];
    }
    readonly property color bg: colors.bg
    readonly property color sidebar: colors.sidebar
    readonly property color panel: colors.panel
    readonly property color field: colors.field
    readonly property color border: colors.border
    readonly property color strongBorder: colors.strongBorder
    readonly property color fg: colors.fg
    readonly property color muted: colors.muted
    readonly property color dim: colors.dim
    readonly property color accent: colors.accent
    readonly property color accentText: colors.accentText
    readonly property color accentPressed: colors.accentPressed
    readonly property color hover: colors.hover
    readonly property color pressed: colors.pressed
    readonly property color selection: colors.selection
    readonly property color selectedChat: colors.selectedChat
    readonly property color popup: colors.popup
    readonly property color errorBg: colors.errorBg
    readonly property color errorText: colors.errorText
}
