import sys
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer, QSize
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


class PhotoBoothWindow(QMainWindow):
    """Main application window that wires UI widgets to webcam capture logic."""

    STREAM_INTERVAL_MS = 30
    COUNTDOWN_SECONDS = 10
    COUNTDOWN_INTERVAL_MS = 1000
    AUTOCAPTURE_INTERVAL_MS = 10_000

    def __init__(self):
        super().__init__()
        self.setWindowTitle("3-Cut Photo Booth")
        self.resize(1280, 800)

        # State holders
        self.current_frame = None
        self.countdown_remaining = self.COUNTDOWN_SECONDS
        self.captured_frames = []
        self.output_dir = Path.cwd() / "captures"
        self.output_dir.mkdir(exist_ok=True)

        # Webcam setup
        self.capture = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
        if not self.capture.isOpened():
            raise RuntimeError("Cannot open default webcam")

        # UI construction
        central = QWidget(self)
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(16, 16, 16, 16)

        splitter = QSplitter(Qt.Horizontal, self)
        main_layout.addWidget(splitter)

        preview_panel = QWidget(self)
        gallery_panel = QWidget(self)
        splitter.addWidget(preview_panel)
        splitter.addWidget(gallery_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # Preview panel layout
        self.preview_label = QLabel("카메라 준비 중...", self)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("background-color: #101010; color: white;")

        self.flash_overlay = QLabel(self.preview_label)
        self.flash_overlay.setStyleSheet("background-color: rgba(255, 255, 255, 0.75);")
        self.flash_overlay.hide()

        self.status_label = QLabel("대기 중", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 22px; padding: 12px;")

        self.start_button = QPushButton("시작", self)
        self.start_button.setStyleSheet("padding: 12px 24px; font-size: 20px;")
        self.start_button.clicked.connect(self.begin_countdown)

        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(self.preview_label, stretch=1)
        preview_layout.addWidget(self.status_label)
        preview_layout.addWidget(self.start_button)

        # Gallery panel layout
        self.gallery_list = QListWidget(self)
        self.gallery_list.setViewMode(QListWidget.IconMode)
        self.gallery_list.setIconSize(QSize(160, 120))
        self.gallery_list.setResizeMode(QListWidget.Adjust)
        self.gallery_list.setMovement(QListWidget.Static)

        gallery_layout = QVBoxLayout(gallery_panel)
        gallery_layout.addWidget(self.gallery_list)

        # Timer A: live stream refresh
        self.timer_stream = QTimer(self)
        self.timer_stream.timeout.connect(self.update_frame)
        self.timer_stream.start(self.STREAM_INTERVAL_MS)

        # Timer B: countdown
        self.timer_countdown = QTimer(self)
        self.timer_countdown.timeout.connect(self.update_countdown)

        # Timer C: auto capture interval
        self.timer_autocapture = QTimer(self)
        self.timer_autocapture.timeout.connect(self.handle_auto_capture)

    # ---- Timer / capture handlers -------------------------------------------------

    def update_frame(self):
        """Timer A callback: fetches latest frame and renders into the preview."""
        ok, frame = self.capture.read()
        if not ok:
            self.preview_label.setText("웹캠 신호 없음")
            return

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        image = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.flash_overlay.resize(self.preview_label.size())
        self.current_frame = frame

    def begin_countdown(self):
        """Triggered by the start button to initiate Timer B."""
        if self.timer_countdown.isActive() or self.timer_autocapture.isActive():
            return

        if self.current_frame is None:
            self.status_label.setText("카메라 준비 중입니다...")
            return

        self.countdown_remaining = self.COUNTDOWN_SECONDS
        self.status_label.setText(f"촬영 준비... {self.countdown_remaining}")
        self.start_button.setEnabled(False)
        self.timer_countdown.start(self.COUNTDOWN_INTERVAL_MS)

    def update_countdown(self):
        """Timer B callback: updates countdown every second."""
        self.countdown_remaining -= 1
        if self.countdown_remaining > 0:
            self.status_label.setText(f"촬영 준비... {self.countdown_remaining}")
            return

        # Countdown finished
        self.timer_countdown.stop()
        self.status_label.setText("촬영 시작!")
        self.trigger_flash()
        self.capture_frame(auto=True)
        self.timer_autocapture.start(self.AUTOCAPTURE_INTERVAL_MS)

    def handle_auto_capture(self):
        """Timer C callback: perform auto capture every interval."""
        self.status_label.setText("자동 촬영 중...")
        self.trigger_flash()
        self.capture_frame(auto=True)

    def trigger_flash(self):
        """Simple flash effect overlay on the preview."""
        self.flash_overlay.show()
        QTimer.singleShot(150, self.flash_overlay.hide)

    def capture_frame(self, auto=False):
        """Capture the current frame and add to the gallery."""
        if self.current_frame is None:
            return

        frame = self.current_frame.copy()
        index = len(self.captured_frames) + 1
        filename = self.output_dir / f"capture_{index:03d}.png"
        cv2.imwrite(str(filename), frame)
        self.captured_frames.append(filename)

        # Thumbnail for gallery
        thumb_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        thumb_image = QImage(
            thumb_rgb.data,
            thumb_rgb.shape[1],
            thumb_rgb.shape[0],
            thumb_rgb.shape[1] * thumb_rgb.shape[2],
            QImage.Format_RGB888,
        )
        thumb_icon = QPixmap.fromImage(thumb_image).scaled(
            self.gallery_list.iconSize(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        item = QListWidgetItem()
        item.setText(filename.name)
        item.setData(Qt.UserRole, str(filename))
        item.setIcon(thumb_icon)
        self.gallery_list.addItem(item)

        if auto:
            self.status_label.setText("자동 촬영 완료")
        else:
            self.status_label.setText("수동 촬영 완료")

    # ---- Qt lifecycle -------------------------------------------------------------

    def closeEvent(self, event):
        if self.timer_stream.isActive():
            self.timer_stream.stop()
        if self.timer_countdown.isActive():
            self.timer_countdown.stop()
        if self.timer_autocapture.isActive():
            self.timer_autocapture.stop()

        if self.capture.isOpened():
            self.capture.release()
        cv2.destroyAllWindows()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = PhotoBoothWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()