import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import qs.Ui
import qs.Commons

// Standalone settings panel. It is summonable from the Omarchy menu.
Panel {
  id: root
  moduleName: "io.github.sahzudin.hotcorners"
  manageIpc: false

  readonly property var primaryScreen: Quickshell.screens.length > 0 ? Quickshell.screens[0] : null
  readonly property int gap: Style.gapsOut
  property bool focusPrimed: false

  function beginFocusPrime() {
    if (!root.opened || !win.backingWindowVisible) return
    root.focusPrimed = false
    focusPrimeTimer.restart()
    Qt.callLater(function() { if (root.opened) content.takeFocus() })
  }

  onOpenedChanged: {
    if (opened) {
      content.refresh()
      beginFocusPrime()
    } else {
      focusPrimeTimer.stop()
      focusPrimed = false
    }
  }

  Timer {
    id: focusPrimeTimer
    interval: 75
    onTriggered: if (root.opened) root.focusPrimed = true
  }

  PanelWindow {
    id: win
    screen: root.primaryScreen
    visible: root.opened
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore

    WlrLayershell.namespace: "omarchy-hotcorners-panel"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.opened
      ? WlrKeyboardFocus.Exclusive
      : WlrKeyboardFocus.None

    onBackingWindowVisibleChanged: root.beginFocusPrime()

    anchors {
      top: true
      bottom: true
      left: true
      right: true
    }

    MouseArea {
      anchors.fill: parent
      enabled: root.opened
      onClicked: root.close()
    }

    BorderSurface {
      id: card
      anchors.centerIn: parent
      width: Math.min(Style.space(560), parent.width - root.gap * 2)
      // Track the content instead of pinning a fixed height — the custom
      // command fields appear and disappear, and a fixed card leaves dead
      // space under the footer when they are hidden.
      height: Math.min(
        content.implicitHeight + card.contentTopInset + card.contentBottomInset,
        parent.height - root.gap * 2)

      color: Color.popups.background
      borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
      padding: Style.spacing.panelPadding
      radius: Style.cornerRadius

      Behavior on height {
        NumberAnimation { duration: 140; easing.type: Easing.OutQuad }
      }

      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
      }

      Item {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset

        HotcornersContent {
          id: content
          anchors.fill: parent
          onCloseRequested: root.close()
        }
      }
    }
  }
}