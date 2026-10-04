"""The file type viewer's preview pane: a large picture and facts about the selection."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFont, QImageReader, QPainter
from PySide6.QtWidgets import QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..core.categories import Kind, kind_of_extension
from ..core.formatting import format_count, format_size
from ..core.model import FileNode
from ..core.system import IS_WINDOWS
from .state import ViewState
from .theme import ThemeManager
from .thumbnails import ThumbnailProvider, size_step
from .viewer_results import date_text, fit, paint_badge, paint_placeholder, type_text
from .widgets import ElidedLabel, FlowLayout, labelled

REVEAL_LABEL = "Show in Explorer" if IS_WINDOWS else "Show in folder"


class PreviewPicture(QWidget):
    def __init__(self, state: ViewState, themes: ThemeManager, thumbnails: ThumbnailProvider,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.themes = themes
        self.thumbnails = thumbnails
        self._node: FileNode | None = None
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        themes.changed.connect(self.update)

    def set_file(self, node: FileNode | None) -> None:
        self._node = node
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(300, 260)

    def paintEvent(self, event) -> None:
        node, tree = self._node, self.state.tree
        if node is None or tree is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ratio = self.devicePixelRatioF()
        box = QRectF(self.rect())
        image = self.thumbnails.image(tree.path_of(node), size_step(max(box.width(), box.height()) * ratio),
                                      node.cloud > 0)
        if image is not None and not image.isNull():
            target = fit(image, box, ratio)
            p.drawImage(target, image)
        else:
            side = min(box.width(), box.height(), 220.0)
            target = QRectF(box.center().x() - side / 2, box.center().y() - side / 2, side, side)
            paint_placeholder(p, target, node, self.themes.theme, self.font())
        if kind_of_extension(node.ext) == Kind.VIDEOS:
            paint_badge(p, target.left() + 22, target.bottom() - 22, "play", radius=15)
        if node.cloud:
            paint_badge(p, target.right() - 22, target.top() + 22, "cloud", radius=15)


class PreviewPanel(QWidget):
    actionRequested = Signal(str, list)  # "open" | "reveal" | "chart" | "copy", files

    def __init__(self, state: ViewState, themes: ThemeManager, thumbnails: ThumbnailProvider,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._files: list[FileNode] = []

        self.picture = PreviewPicture(state, themes, thumbnails)
        self.name = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
        bold = QFont(self.name.font())
        bold.setPointSizeF(bold.pointSizeF() + 1.5)
        bold.setWeight(QFont.Weight.DemiBold)
        self.name.setFont(bold)
        self.size = labelled("", "secondary", elide=Qt.TextElideMode.ElideRight)
        self.kind = labelled("", "secondary", elide=Qt.TextElideMode.ElideRight)
        self.dimensions = labelled("", "muted", elide=Qt.TextElideMode.ElideRight)
        self.modified = labelled("", "muted", elide=Qt.TextElideMode.ElideRight)
        self.folder = labelled("", "muted", elide=Qt.TextElideMode.ElideMiddle)
        self.hint = labelled("Select a file to see it here. Double-click opens it.", "muted")
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.buttons: dict[str, QPushButton] = {}
        actions = QWidget()
        row = FlowLayout(actions, spacing=6)
        row.setContentsMargins(0, 6, 0, 0)
        for key, label in (("open", "Open"), ("reveal", REVEAL_LABEL), ("chart", "Show in chart"),
                           ("copy", "Copy path")):
            button = QPushButton(label)
            button.setProperty("compact", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self.actionRequested.emit(k, list(self._files)))
            self.buttons[key] = button
            row.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(3)
        layout.addWidget(self.picture, 1)
        layout.addSpacing(8)
        for label in (self.name, self.size, self.kind, self.dimensions, self.modified, self.folder):
            layout.addWidget(label)
        layout.addWidget(self.hint, 1)
        layout.addWidget(actions)
        self.show_files([])

    def show_files(self, files: list[FileNode]) -> None:
        self._files = files
        tree = self.state.tree
        details = (self.name, self.size, self.kind, self.dimensions, self.modified, self.folder)
        if not files or tree is None:
            self.picture.set_file(None)
            self.picture.hide()
            for label in details:
                label.hide()
            self.hint.show()
            for button in self.buttons.values():
                button.setEnabled(False)
            return
        self.hint.hide()
        for button in self.buttons.values():
            button.setEnabled(True)
        if len(files) > 1:
            self.picture.set_file(files[0])
            self.picture.show()
            self.name.setFullText(f"{format_count(len(files), 'file')} selected")
            total = sum(f.size + f.cloud for f in files)
            self.size.setFullText(format_size(total))
            for label in (self.kind, self.dimensions, self.modified, self.folder):
                label.hide()
            self.name.show()
            self.size.show()
            self.buttons["open"].setEnabled(False)
            self.buttons["copy"].setText("Copy paths")
            return
        node = files[0]
        self.picture.set_file(node)
        self.picture.show()
        self.buttons["copy"].setText("Copy path")
        self.name.setFullText(node.name)
        size = format_size(node.size + node.cloud)
        if node.cloud:
            size += "  ·  online-only, not stored on this PC"
        self.size.setFullText(size)
        self.kind.setFullText(type_text(node))
        self.dimensions.setFullText(self._dimensions(tree.path_of(node), node))
        self.modified.setFullText(f"Modified {date_text(node.mtime)}" if node.mtime > 0 else "")
        self.folder.setFullText(tree.path_of(node.parent))
        for label in details:
            label.setVisible(bool(label.fullText()))

    @staticmethod
    def _dimensions(path: str, node: FileNode) -> str:
        """'4032 x 3024 pixels' for pictures stored on this PC (reads only the file's header)."""
        if node.cloud or kind_of_extension(node.ext) != Kind.PHOTOS:
            return ""
        size = QImageReader(path).size()
        if not size.isValid():
            return ""
        return f"{size.width():,} × {size.height():,} pixels"

    def refresh_picture(self) -> None:
        self.picture.update()

    def clear(self) -> None:
        self.show_files([])
