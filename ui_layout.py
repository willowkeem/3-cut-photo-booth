#PyQt UI 레이아웃 코드
import sys
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


class PhotoBooth(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Webcam Preview with Gallery")
        self.resize(1200, 720)

        # webcam capture
        self.capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.capture.isOpened():
            raise RuntimeError("Cannot open default webcam")

        # UI setup
        central = QWidget(self)
        self.setCentralWidget(central)

        # splitter separates preview (left) and gallery (right)
        splitter = QSplitter(Qt.Horizontal, self)
        preview_widget = QWidget(self)
        gallery_widget = QWidget(self)

        splitter.addWidget(preview_widget)
        splitter.addWidget(gallery_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Preview layout
        self.preview_label = QLabel("Initializing camera...", self)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("background-color: #101010; color: white;")

        capture_btn = QPushButton("Capture", self)
        capture_btn.clicked.connect(self.capture_frame)

        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.addWidget(self.preview_label, stretch=1)
        preview_layout.addWidget(capture_btn, stretch=0)

        # Gallery layout
        self.gallery_list = QListWidget(self)
        self.gallery_list.setViewMode(QListWidget.IconMode)
        self.gallery_list.setIconSize(Qt.QSize(160, 120))
        self.gallery_list.setResizeMode(QListWidget.Adjust)
        self.gallery_list.setMovement(QListWidget.Static)
        self.gallery_list.itemDoubleClicked.connect(self.show_full_frame)

        gallery_layout = QVBoxLayout(gallery_widget)
        gallery_layout.addWidget(self.gallery_list)

        main_layout = QHBoxLayout(central)
        main_layout.addWidget(splitter)

        # timer for webcam preview
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)

        # storage for captured frames (optional)
        self.captured_frames = []
        self.output_dir = Path.cwd() / "captures"
        self.output_dir.mkdir(exist_ok=True)

    def update_frame(self):
        ok, frame = self.capture.read()
        if not ok:
            self.preview_label.setText("Failed to read frame")
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        image = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(image).scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        ))

        self.current_frame = frame

    def capture_frame(self):
        if not hasattr(self, "current_frame"):
            return

        frame = self.current_frame.copy()
        index = len(self.captured_frames) + 1
        filename = self.output_dir / f"capture_{index:03d}.png"
        cv2.imwrite(str(filename), frame)
        self.captured_frames.append(filename)

        thumb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        thumb_qimg = QImage(
            thumb.data,
            thumb.shape[1],
            thumb.shape[0],
            thumb.shape[1] * thumb.shape[2],
            QImage.Format_RGB888,
        )
        item = QListWidgetItem()
        item.setText(filename.name)
        item.setData(Qt.UserRole, str(filename))
        item.setIcon(QPixmap.fromImage(thumb_qimg).scaled(
            160, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        self.gallery_list.addItem(item)

    def show_full_frame(self, item):
        path = Path(item.data(Qt.UserRole))
        if not path.exists():
            return

        frame = cv2.imread(str(path))
        if frame is None:
            return

        cv2.imshow(path.name, frame)

    def closeEvent(self, event):
        if self.capture.isOpened():
            self.capture.release()
        cv2.destroyAllWindows()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = PhotoBooth()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()