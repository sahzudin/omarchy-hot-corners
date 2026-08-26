import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

FocusScope {
  id: root

  signal closeRequested()

  // The card sizes itself to whatever the layout needs, so the panel never
  // leaves a slab of empty background under the footer.
  implicitHeight: layout.implicitHeight

  readonly property string backendPath: {
    var url = String(Qt.resolvedUrl("scripts/hotcorners.py"))
    return url.indexOf("file://") === 0 ? url.substring(7) : url
  }

  property var corners: ({})
  property var custom: ({})
  property var options: ({ "dwell": 250, "corner": 10, "edge": 4 })
  property var actions: []
  property bool installed: true
  property bool busy: false
  property string statusText: "Loading hot corners…"
  property bool statusIsError: false

  // `loading` suppresses the dirty flag while onListResult writes the
  // backend's values into the controls — those writes are not user edits.
  property bool loading: true
  property bool dirty: false

  // The corner the pointer is currently over, whether that pointer is on the
  // diagram or on the matching dropdown. Both surfaces highlight from it, so
  // the mapping between a corner and its control is always visible.
  property string hoveredCorner: ""

  readonly property color dim: Qt.darker(Color.foreground, 1.45)
  readonly property color faint: Qt.darker(Color.foreground, 1.9)

  readonly property var cornerKeys: ["top-left", "top-right", "bottom-left", "bottom-right"]

  readonly property var actionOptions: root.actions.map(function(a) {
    return { value: a.id, label: a.label }
  })

  readonly property int activeCount: {
    var n = 0
    for (var i = 0; i < root.cornerKeys.length; i++) {
      if (root.isActive(root.cornerKeys[i])) n++
    }
    return n
  }

  // Center caption of the diagram: idle it names the surface, on hover it
  // spells out the full action the short corner chip had to abbreviate.
  readonly property string diagramCaption: root.hoveredCorner === ""
    ? "screen"
    : root.actionLabel(root.currentAction(root.hoveredCorner))

  function currentAction(corner) {
    return String((root.corners && root.corners[corner]) || "none")
  }

  function isActive(corner) {
    return root.currentAction(corner) !== "none"
  }

  function actionLabel(id) {
    for (var i = 0; i < root.actions.length; i++) {
      if (root.actions[i].id === id) return String(root.actions[i].label)
    }
    return "Disabled"
  }

  function shortLabel(id) {
    var map = {
      "none": "Off", "apps-menu": "Apps", "launcher": "Launcher",
      "show-desktop": "Desktop", "next-workspace": "Next WS",
      "prev-workspace": "Prev WS", "fullscreen": "Fullscreen",
      "close-window": "Close", "custom": "Custom"
    }
    return map[id] || "?"
  }

  function fieldFor(corner) {
    if (corner === "top-left") return fieldTL
    if (corner === "top-right") return fieldTR
    if (corner === "bottom-left") return fieldBL
    return fieldBR
  }

  function setHover(corner, on) {
    if (on) root.hoveredCorner = corner
    else if (root.hoveredCorner === corner) root.hoveredCorner = ""
  }

  function markDirty() {
    if (root.loading || !root.installed) return
    root.dirty = true
    root.statusIsError = false
    root.statusText = "Unsaved changes"
  }

  function parseOutput(raw) {
    try { return JSON.parse(String(raw || "").trim()) }
    catch (error) { return { ok: false, error: "The backend returned invalid data." } }
  }

  function refresh() {
    if (listProcess.running) return
    root.loading = true
    listProcess.command = ["python3", root.backendPath, "list"]
    listProcess.running = true
  }

  function onListResult(raw) {
    var result = root.parseOutput(raw)
    if (!result.ok) {
      root.loading = false
      root.statusIsError = true
      root.statusText = result.error || "Could not load hot corners."
      return
    }
    root.corners = result.corners || {}
    root.custom = result.custom || {}
    root.options = result.options || { dwell: 250, corner: 10, edge: 4 }
    root.actions = result.actions || []
    root.installed = result.installed !== false

    for (var i = 0; i < root.cornerKeys.length; i++) {
      var key = root.cornerKeys[i]
      var field = root.fieldFor(key)
      field.dropdown.value = root.currentAction(key)
      field.command.text = root.custom[key] || ""
    }
    dwellField.value = Number(root.options.dwell) || 250
    cornerField.value = Number(root.options.corner) || 10
    edgeField.value = Number(root.options.edge) || 4

    root.dirty = false
    root.statusIsError = !root.installed
    root.statusText = root.installed
      ? "No unsaved changes"
      : "Hot corners are not installed. Run the plugin install script first."

    // Let the control writes above settle before edits count as user intent.
    Qt.callLater(function() { root.loading = false })
  }

  function onChangeResult(raw) {
    root.busy = false
    var result = root.parseOutput(raw)
    if (!result.ok) {
      root.statusIsError = true
      root.statusText = result.error || "Could not save settings."
      return
    }
    root.dirty = false
    root.statusIsError = false
    root.statusText = "Settings applied"
  }

  function save() {
    if (root.busy) return
    root.busy = true
    root.statusIsError = false
    root.statusText = "Applying settings…"
    changeProcess.command = ["python3", root.backendPath, "apply", JSON.stringify(root.collectPayload())]
    changeProcess.running = true
  }

  function resetAll() {
    if (root.busy) return
    root.busy = true
    root.statusIsError = false
    root.statusText = "Restoring defaults…"
    changeProcess.command = ["python3", root.backendPath, "reset"]
    changeProcess.running = true
  }

  function collectPayload() {
    return {
      corners: {
        "top-left": fieldTL.dropdown.value, "top-right": fieldTR.dropdown.value,
        "bottom-left": fieldBL.dropdown.value, "bottom-right": fieldBR.dropdown.value
      },
      custom: {
        "top-left": fieldTL.command.text, "top-right": fieldTR.command.text,
        "bottom-left": fieldBL.command.text, "bottom-right": fieldBR.command.text
      },
      options: {
        dwell: dwellField.value, corner: cornerField.value, edge: edgeField.value
      }
    }
  }

  function takeFocus() {
    fieldTL.dropdown.forceActiveFocus()
  }

  Component.onCompleted: root.refresh()

  Keys.onEscapePressed: root.closeRequested()

  Process {
    id: listProcess
    command: []
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.onListResult(text)
    }
  }

  Process {
    id: changeProcess
    command: []
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.onChangeResult(text)
    }
  }

  Column {
    id: layout
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    spacing: Style.spacing.panelGap

    // ---------------------------------------------------------- header
    PanelHero {
      width: parent.width
      title: "Hot Corners"
      meta: "Pick an action for each screen corner"
      detail: root.installed ? (root.activeCount + "/4") : ""
      foreground: Color.foreground
      iconComponent: Component { HeroGlyph {} }
    }

    PanelSeparator { foreground: Color.foreground }

    // ---------------------------------------------------------- diagram
    //
    // The four corner chips are flush with the frame and carry the outer
    // radius of the screen they sit in, so the map reads as a screen with
    // its corners armed rather than as four floating buttons.
    Rectangle {
      id: diagram
      anchors.horizontalCenter: parent.horizontalCenter
      width: Math.min(parent.width, Style.space(360))
      height: Style.space(168)
      radius: Style.cornerRadius
      color: Util.alpha(Color.foreground, 0.03)
      border.width: Math.max(1, Style.normalBorderWidth)
      border.color: Util.alpha(Color.foreground, 0.24)

      Item {
        anchors.fill: parent
        anchors.margins: diagram.border.width

        CornerHotspot {
          corner: "top-left"
          anchors.left: parent.left
          anchors.top: parent.top
        }
        CornerHotspot {
          corner: "top-right"
          anchors.right: parent.right
          anchors.top: parent.top
        }
        CornerHotspot {
          corner: "bottom-left"
          anchors.left: parent.left
          anchors.bottom: parent.bottom
        }
        CornerHotspot {
          corner: "bottom-right"
          anchors.right: parent.right
          anchors.bottom: parent.bottom
        }

        Text {
          id: caption
          anchors.centerIn: parent
          width: parent.width - Style.space(48)
          text: root.diagramCaption
          textFormat: Text.PlainText
          color: root.hoveredCorner === "" ? root.faint : root.dim
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          horizontalAlignment: Text.AlignHCenter
          elide: Text.ElideRight

          Behavior on color { ColorAnimation { duration: 140 } }
        }
      }
    }

    PanelSeparator { foreground: Color.foreground }

    // ---------------------------------------------------------- corners
    Column {
      width: parent.width
      spacing: Style.spacing.xl

      PanelSectionHeader {
        text: "CORNER ACTIONS"
        foreground: Color.foreground
        font.letterSpacing: 1.2
      }

      Row {
        width: parent.width
        spacing: Style.spacing.xxl

        CornerField {
          id: fieldTL
          width: (parent.width - parent.spacing) / 2
          corner: "top-left"
          title: "Top-left"
        }
        CornerField {
          id: fieldTR
          width: (parent.width - parent.spacing) / 2
          corner: "top-right"
          title: "Top-right"
        }
      }

      Row {
        width: parent.width
        spacing: Style.spacing.xxl

        CornerField {
          id: fieldBL
          width: (parent.width - parent.spacing) / 2
          corner: "bottom-left"
          title: "Bottom-left"
        }
        CornerField {
          id: fieldBR
          width: (parent.width - parent.spacing) / 2
          corner: "bottom-right"
          title: "Bottom-right"
        }
      }
    }

    PanelSeparator { foreground: Color.foreground }

    // ---------------------------------------------------------- tuning
    Column {
      width: parent.width
      spacing: Style.spacing.xl

      PanelSectionHeader {
        text: "SENSITIVITY"
        foreground: Color.foreground
        font.letterSpacing: 1.2
      }

      Row {
        width: parent.width
        spacing: Style.spacing.xxl

        TuningField {
          id: dwellField
          width: (parent.width - parent.spacing * 2) / 3
          title: "Hold time (ms)"
          from: 0
          to: 2000
          stepSize: 50
        }
        TuningField {
          id: cornerField
          width: (parent.width - parent.spacing * 2) / 3
          title: "Corner size (px)"
          from: 1
          to: 100
          stepSize: 1
        }
        TuningField {
          id: edgeField
          width: (parent.width - parent.spacing * 2) / 3
          title: "Edge size (px)"
          from: 1
          to: 100
          stepSize: 1
        }
      }
    }

    PanelSeparator { foreground: Color.foreground }

    // ---------------------------------------------------------- footer
    Item {
      width: parent.width
      height: Math.max(statusRow.implicitHeight, footerButtons.implicitHeight)

      Item {
        id: statusRow
        anchors.left: parent.left
        anchors.right: footerButtons.left
        anchors.rightMargin: Style.spacing.xxl
        anchors.verticalCenter: parent.verticalCenter
        implicitHeight: statusLabel.implicitHeight

        // Pulsing pip: unsaved edits are pending, or the last call failed.
        Rectangle {
          id: statusPip
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          width: Style.space(6)
          height: width
          radius: width / 2
          visible: root.dirty || root.statusIsError
          color: root.statusIsError ? Color.urgent : Color.accent

          SequentialAnimation on opacity {
            running: statusPip.visible
            loops: Animation.Infinite
            NumberAnimation { to: 0.3; duration: 900; easing.type: Easing.InOutQuad }
            NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
          }
        }

        Text {
          id: statusLabel
          anchors.left: statusPip.visible ? statusPip.right : parent.left
          anchors.leftMargin: statusPip.visible ? Style.spacing.lg : 0
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          text: root.statusText
          textFormat: Text.PlainText
          color: root.statusIsError ? Color.urgent : root.dim
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          elide: Text.ElideRight
        }
      }

      Row {
        id: footerButtons
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.spacing.lg

        Button {
          text: "Reset"
          tooltipText: "Restore the default corner actions"
          bordered: true
          focusable: true
          enabled: !root.busy && root.installed
          opacity: enabled ? 1.0 : 0.4
          onClicked: root.resetAll()
        }

        // Primary action: accent-tinted fill so the commit step reads
        // ahead of the destructive one next to it.
        Button {
          text: "Save"
          tooltipText: "Apply the current settings"
          bordered: true
          focusable: true
          foreground: Color.accent
          background: Style.selectedAccentFill
          enabled: !root.busy && root.installed
          opacity: enabled ? 1.0 : 0.4
          onClicked: root.save()
        }
      }
    }
  }

  // A miniature of the diagram below, so the hero icon says what the panel
  // does without depending on a glyph the user's font may not carry.
  component HeroGlyph: Item {
    id: glyph
    readonly property real box: Style.space(24)
    readonly property real pip: Math.max(2, Style.space(6))

    implicitWidth: box
    implicitHeight: box

    Rectangle {
      anchors.fill: parent
      radius: Math.max(1, Style.space(3))
      color: "transparent"
      border.width: Math.max(1, Style.normalBorderWidth)
      border.color: Util.alpha(Color.foreground, 0.45)
    }

    Repeater {
      model: root.cornerKeys

      Rectangle {
        required property string modelData
        readonly property bool atLeft: modelData.indexOf("left") >= 0
        readonly property bool atTop: modelData.indexOf("top") >= 0

        width: glyph.pip
        height: glyph.pip
        x: atLeft ? 0 : glyph.box - width
        y: atTop ? 0 : glyph.box - height
        radius: Math.max(1, Style.space(2))
        color: root.isActive(modelData) ? Color.accent : Util.alpha(Color.foreground, 0.22)

        Behavior on color { ColorAnimation { duration: 160 } }
      }
    }
  }

  component CornerHotspot: Rectangle {
    id: spot

    property string corner: ""

    readonly property bool atLeft: corner.indexOf("left") >= 0
    readonly property bool atTop: corner.indexOf("top") >= 0
    readonly property bool armed: root.isActive(corner)
    readonly property bool hot: root.hoveredCorner === corner

    width: Style.space(128)
    height: Style.space(46)

    // Square off against the frame, round toward the middle of the screen.
    radius: Style.space(12)
    topLeftRadius: (atTop && atLeft) ? Style.cornerRadius : radius
    topRightRadius: (atTop && !atLeft) ? Style.cornerRadius : radius
    bottomLeftRadius: (!atTop && atLeft) ? Style.cornerRadius : radius
    bottomRightRadius: (!atTop && !atLeft) ? Style.cornerRadius : radius

    color: armed
      ? Util.alpha(Color.accent, hot ? 0.28 : 0.15)
      : Util.alpha(Color.foreground, hot ? 0.10 : 0.04)
    border.width: Math.max(1, Style.normalBorderWidth)
    border.color: armed
      ? Util.alpha(Color.accent, hot ? 1.0 : 0.65)
      : Util.alpha(Color.foreground, hot ? 0.40 : 0.14)

    Behavior on color { ColorAnimation { duration: 140 } }
    Behavior on border.color { ColorAnimation { duration: 140 } }

    Text {
      anchors.fill: parent
      anchors.margins: Style.spacing.md
      text: root.shortLabel(root.currentAction(spot.corner))
      textFormat: Text.PlainText
      color: spot.armed ? Color.foreground : root.faint
      font.family: Style.font.family
      font.pixelSize: Style.font.bodySmall
      font.bold: spot.armed
      horizontalAlignment: Text.AlignHCenter
      verticalAlignment: Text.AlignVCenter
      elide: Text.ElideRight
      maximumLineCount: 1

      Behavior on color { ColorAnimation { duration: 140 } }
    }

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setHover(spot.corner, true)
      onExited: root.setHover(spot.corner, false)
      onClicked: {
        var field = root.fieldFor(spot.corner)
        field.dropdown.forceActiveFocus()
        field.dropdown.open()
      }
    }
  }

  // NumberField labels its own field in a lighter, larger style than
  // Dropdown does; relabel it here so every control in the card has the
  // same caption above it.
  component TuningField: Column {
    id: tune

    property string title: ""
    property alias value: nf.value
    property alias from: nf.from
    property alias to: nf.to
    property alias stepSize: nf.stepSize

    spacing: Style.spacing.labelGap

    Text {
      text: tune.title
      textFormat: Text.PlainText
      color: root.dim
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      font.bold: true
    }

    NumberField {
      id: nf
      width: tune.width
      fieldWidth: tune.width
      enabled: !root.busy
      onModified: root.markDirty()
    }
  }

  component CornerField: Column {
    id: field

    property string corner: ""
    property string title: ""
    property alias dropdown: dd
    property alias command: cmd

    spacing: Style.spacing.md

    Dropdown {
      id: dd
      width: field.width
      label: field.title
      options: root.actionOptions
      enabled: !root.busy && root.installed
      hasCursor: root.hoveredCorner === field.corner
      onHovered: function(on) { root.setHover(field.corner, on) }
      onChanged: function(value) {
        var next = Object.assign({}, root.corners)
        next[field.corner] = value
        root.corners = next
        root.markDirty()
      }
    }

    TextField {
      id: cmd
      width: field.width
      visible: dd.value === "custom"
      placeholderText: "Command, e.g. uwsm-app -- firefox"
      enabled: !root.busy
      onTextChanged: root.markDirty()
    }
  }
}
