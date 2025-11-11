import sys
from datetime import datetime
from pathlib import Path
from typing import List

import cv2
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QImage, QPixmap, QIcon

from image_processor import combine_three_images
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
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
    COUNTDOWN_SECONDS = 5  # 초기 카운트다운 5초
    COUNTDOWN_INTERVAL_MS = 1000
    CAPTURE_INTERVAL_SECONDS = 5  # 촬영 사이 카운트다운 5초
    CAPTURE_INTERVAL_MS = 5000
    MAX_CAPTURES = 8  # 8장 촬영
    SELECT_COUNT = 3  # 그 중 3장 선택

    def __init__(self):
        super().__init__()
        self.setWindowTitle("3-Cut Photo Booth")
        self.resize(1280, 800)

        # State holders
        self.current_frame = None
        self.countdown_remaining = self.COUNTDOWN_SECONDS
        self.capture_countdown_remaining = 0  # 촬영 사이 카운트다운
        self.captured_frames = []
        self.selected_frames = []  # 선택된 3장
        self.output_dir = Path.cwd() / "captures"
        self.output_dir.mkdir(exist_ok=True)
        self.is_capture_countdown = False  # 촬영 사이 카운트다운 중인지

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
        self.preview_label = QLabel("Camera is initialising...", self)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("background-color: #101010; color: white;")

        self.flash_overlay = QLabel(self.preview_label)
        self.flash_overlay.setStyleSheet("background-color: rgba(255, 255, 255, 0.75);")
        self.flash_overlay.hide()

        # 카운트다운 오버레이 (큰 숫자 표시)
        self.countdown_overlay = QLabel(self.preview_label)
        self.countdown_overlay.setAlignment(Qt.AlignCenter)
        self.countdown_overlay.setStyleSheet(
            "background-color: rgba(0, 0, 0, 0.7); "
            "color: white; "
            "font-size: 150px; "
            "font-weight: bold; "
            "border-radius: 20px;"
        )
        self.countdown_overlay.hide()

        self.status_label = QLabel("Ready to record", self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 22px; padding: 12px;")

        self.start_button = QPushButton("Action!", self)
        self.start_button.setStyleSheet("padding: 12px 24px; font-size: 20px;")
        self.start_button.clicked.connect(self.begin_countdown)

        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(self.preview_label, stretch=1)
        preview_layout.addWidget(self.status_label)
        preview_layout.addWidget(self.start_button)

        # Gallery panel layout - 세로로 나누기
        gallery_splitter = QSplitter(Qt.Vertical, self)
        
        # 상단: 전체 갤러리
        gallery_top = QWidget(self)
        self.gallery_list = QListWidget(self)
        self.gallery_list.setViewMode(QListWidget.IconMode)
        self.gallery_list.setIconSize(QSize(160, 120))
        self.gallery_list.setResizeMode(QListWidget.Adjust)
        self.gallery_list.setMovement(QListWidget.Static)
        self.gallery_list.setSelectionMode(QListWidget.MultiSelection)  # 다중 선택 활성화
        self.gallery_list.itemSelectionChanged.connect(self.on_selection_changed)
        # 파일명 텍스트 숨기기 스타일
        self.gallery_list.setStyleSheet(
            "QListWidget::item { "
            "height: 140px; "
            "padding: 5px; "
            "}"
            "QListWidget::item::text { "
            "color: transparent; "
            "height: 0px; "
            "}"
        )

        # 선택 상태 표시 레이블
        self.selection_label = QLabel("Select photos (0/3)", self)
        self.selection_label.setAlignment(Qt.AlignCenter)
        self.selection_label.setStyleSheet("font-size: 16px; padding: 8px;")

        gallery_top_layout = QVBoxLayout(gallery_top)
        gallery_top_layout.addWidget(QLabel("Captured Photos (Select 3 of 8)", self))
        gallery_top_layout.addWidget(self.gallery_list, stretch=1)
        gallery_top_layout.addWidget(self.selection_label)

        # 하단: 선택된 3장 미리보기
        preview_bottom = QWidget(self)
        preview_bottom.setMinimumHeight(250)
        
        # 메인 레이아웃
        preview_bottom_layout = QVBoxLayout(preview_bottom)
        preview_bottom_layout.setContentsMargins(10, 10, 10, 10)
        preview_bottom_layout.setSpacing(10)
        
        # 제목
        preview_title = QLabel("Preview", self)
        preview_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        preview_bottom_layout.addWidget(preview_title)
        
        # 선택된 3장을 표시할 레이블들 (가로 레이아웃)
        self.selected_preview_layout = QHBoxLayout()
        self.selected_preview_layout.setSpacing(10)
        self.selected_preview_labels = []
        for i in range(self.SELECT_COUNT):
            label = QLabel(f"Photo {i+1}", self)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumSize(140, 160)
            label.setMaximumSize(200, 200)
            label.setStyleSheet(
                "border: 2px dashed #ccc; "
                "background-color: #f0f0f0; "
                "color: #999; "
                "font-size: 14px;"
            )
            self.selected_preview_labels.append(label)
            self.selected_preview_layout.addWidget(label)
        
        preview_bottom_layout.addLayout(self.selected_preview_layout)
        
        # 선택 완료 버튼
        self.finalize_button = QPushButton("Complete Selection (0/3 Photos)", self)
        self.finalize_button.setStyleSheet(
            "padding: 15px 30px; "
            "font-size: 18px; "
            "font-weight: bold; "
            "background-color: #9E9E9E; "
            "color: white; "
            "border-radius: 5px;"
        )
        self.finalize_button.setEnabled(False)
        self.finalize_button.clicked.connect(self.finalize_selection)
        preview_bottom_layout.addWidget(self.finalize_button)

        gallery_splitter.addWidget(gallery_top)
        gallery_splitter.addWidget(preview_bottom)
        gallery_splitter.setStretchFactor(0, 2)
        gallery_splitter.setStretchFactor(1, 1)

        gallery_layout = QVBoxLayout(gallery_panel)
        gallery_layout.addWidget(gallery_splitter)

        # Timer A: live stream refresh
        self.timer_stream = QTimer(self)
        self.timer_stream.timeout.connect(self.update_frame)
        self.timer_stream.start(self.STREAM_INTERVAL_MS)

        # Timer B: countdown (초기 카운트다운 및 촬영 사이 카운트다운)
        self.timer_countdown = QTimer(self)
        self.timer_countdown.timeout.connect(self.update_countdown)

    # ---- Timer / capture handlers -------------------------------------------------

    def update_frame(self):
        """Timer A callback: fetches latest frame and renders into the preview."""
        try:
            ok, frame = self.capture.read()
            if not ok:
                self.preview_label.setText("No Camera Signal")
                return

            if frame is None or frame.size == 0:
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
            self.countdown_overlay.resize(self.preview_label.size())
            self.current_frame = frame
        except Exception as e:
            # 예외 발생 시에도 앱이 계속 실행되도록
            print(f"Frame update error: {e}")  # 디버깅용

    def begin_countdown(self):
        """Triggered by the start button to initiate Timer B."""
        if self.timer_countdown.isActive():
            return

        if self.current_frame is None:
            self.status_label.setText("Camera is initialising...")
            return

        # 재시작 시 상태 초기화
        self.captured_frames = []
        self.selected_frames = []
        self.gallery_list.clear()
        self.finalize_button.setEnabled(False)
        self.finalize_button.setText("Complete Selection (0/3 Photos)")
        self.finalize_button.setStyleSheet(
            "padding: 15px 30px; "
            "font-size: 18px; "
            "font-weight: bold; "
            "background-color: #9E9E9E; "
            "color: white; "
            "border-radius: 5px;"
        )
        self.selection_label.setText("Select photos (0/3)")
        self.countdown_overlay.hide()
        self.is_capture_countdown = False
        
        # 선택된 미리보기 초기화
        for i, label in enumerate(self.selected_preview_labels):
            label.clear()
            label.setText(f"Photo {i + 1}")

        self.countdown_remaining = self.COUNTDOWN_SECONDS
        self.status_label.setText(f"Ready to record... {self.countdown_remaining}")
        self.start_button.setEnabled(False)
        self.start_button.setText("Action!")
        # 초기 카운트다운 시작 (큰 숫자 표시)
        self.countdown_overlay.setText(str(self.countdown_remaining))
        self.countdown_overlay.show()
        self.timer_countdown.start(self.COUNTDOWN_INTERVAL_MS)

    def update_countdown(self):
        """Timer B callback: updates countdown every second."""
        # 촬영 사이 카운트다운 중인 경우
        if self.is_capture_countdown:
            self.capture_countdown_remaining -= 1
            if self.capture_countdown_remaining > 0:
                # 큰 숫자로 카운트다운 표시
                self.countdown_overlay.setText(str(self.capture_countdown_remaining))
                self.countdown_overlay.show()
                self.status_label.setText(f"Next capture in {self.capture_countdown_remaining}...")
                return
            
            # 촬영 사이 카운트다운 완료
            self.countdown_overlay.hide()
            self.is_capture_countdown = False
            self.status_label.setText("Recording...")
            self.trigger_flash()
            self.capture_frame(auto=True)
            
            # 8장 미만이면 다음 촬영을 위해 카운트다운 시작
            if len(self.captured_frames) < self.MAX_CAPTURES:
                self.start_capture_countdown()
            else:
                # 8장 완료
                self.timer_countdown.stop()
                self.status_label.setText(f"Recording complete! ({self.MAX_CAPTURES} photos) - Select 3 photos")
                self.start_button.setEnabled(True)
                self.start_button.setText("Start Again")
                self.selection_label.setText(f"Recording complete! Select 3 of {self.MAX_CAPTURES} photos (0/{self.SELECT_COUNT})")
            return
        
        # 초기 카운트다운
        self.countdown_remaining -= 1
        if self.countdown_remaining > 0:
            # 큰 숫자로 카운트다운 표시
            self.countdown_overlay.setText(str(self.countdown_remaining))
            self.countdown_overlay.show()
            self.status_label.setText(f"Ready to record... {self.countdown_remaining}")
            return

        # 초기 카운트다운 완료
        self.countdown_overlay.hide()
        self.timer_countdown.stop()
        self.status_label.setText("Recording...")
        self.trigger_flash()
        self.capture_frame(auto=True)
        
        # 8장 미만이면 다음 촬영을 위해 카운트다운 시작
        if len(self.captured_frames) < self.MAX_CAPTURES:
            self.start_capture_countdown()
        else:
            # 이미 8장이면 완료 처리
            self.status_label.setText(f"Recording complete! ({self.MAX_CAPTURES} photos) - Select 3 photos")
            self.start_button.setEnabled(True)
            self.start_button.setText("Start Again")
            self.selection_label.setText(f"Recording complete! Select 3 of {self.MAX_CAPTURES} photos (0/{self.SELECT_COUNT})")
    
    def start_capture_countdown(self):
        """촬영 사이 카운트다운 시작."""
        self.is_capture_countdown = True
        self.capture_countdown_remaining = self.CAPTURE_INTERVAL_SECONDS
        self.countdown_overlay.setText(str(self.capture_countdown_remaining))
        self.countdown_overlay.show()
        self.status_label.setText(f"Next capture in {self.capture_countdown_remaining}...")
        self.timer_countdown.start(self.COUNTDOWN_INTERVAL_MS)


    def trigger_flash(self):
        """Simple flash effect overlay on the preview."""
        self.flash_overlay.show()
        QTimer.singleShot(150, self.flash_overlay.hide)

    def capture_frame(self, auto=False):
        """Capture the current frame and add to the gallery."""
        try:
            if self.current_frame is None:
                self.status_label.setText("Capture failed: No frame")
                return

            # 프레임을 안전하게 복사
            frame = self.current_frame.copy()
            if frame is None or frame.size == 0:
                self.status_label.setText("Capture failed: Invalid frame")
                return

            index = len(self.captured_frames) + 1
            filename = self.output_dir / f"capture_{index:03d}.png"
            
            # 파일 저장 시도
            success = cv2.imwrite(str(filename), frame)
            if not success:
                self.status_label.setText("Capture failed: File save error")
                return
            
            self.captured_frames.append(filename)

            # Thumbnail for gallery - 안전한 메모리 처리
            thumb_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # numpy 배열을 복사하여 QImage가 안전하게 사용할 수 있도록 함
            thumb_rgb_copy = thumb_rgb.copy()
            h, w, ch = thumb_rgb_copy.shape
            bytes_per_line = ch * w
            
            thumb_image = QImage(
                thumb_rgb_copy.data,
                w,
                h,
                bytes_per_line,
                QImage.Format_RGB888,
            )
            
            # QImage가 데이터를 소유하도록 복사본 생성 (메모리 안전성)
            thumb_image = thumb_image.copy()
            
            thumb_pixmap = QPixmap.fromImage(thumb_image).scaled(
                self.gallery_list.iconSize(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            
            # QPixmap을 QIcon으로 변환
            thumb_icon = QIcon(thumb_pixmap)

            item = QListWidgetItem()
            item.setText("")  # 파일명 숨기기
            item.setData(Qt.UserRole, str(filename))
            item.setIcon(thumb_icon)
            self.gallery_list.addItem(item)

            if auto:
                remaining = self.MAX_CAPTURES - len(self.captured_frames)
                if remaining > 0:
                    self.status_label.setText(f"Recording... ({len(self.captured_frames)}/{self.MAX_CAPTURES})")
                else:
                    self.status_label.setText(f"Recording complete! ({self.MAX_CAPTURES} photos)")
            else:
                self.status_label.setText("Manual capturing completed")
                
        except Exception as e:
            # 예외 발생 시 앱이 크래시하지 않도록 처리
            error_msg = f"Capture error: {str(e)}"
            self.status_label.setText(error_msg)
            print(f"Capture error: {e}")  # 디버깅용

    # ---- Selection handlers -------------------------------------------------------

    def on_selection_changed(self):
        """갤러리에서 선택이 변경될 때 호출되는 핸들러."""
        selected_items = self.gallery_list.selectedItems()
        selected_count = len(selected_items)
        
        # 최대 3장까지만 선택 가능
        if selected_count > self.SELECT_COUNT:
            # 3장 초과 선택 시 가장 오래된 선택 해제
            for item in selected_items[:-self.SELECT_COUNT]:
                item.setSelected(False)
            selected_count = self.SELECT_COUNT
            selected_items = self.gallery_list.selectedItems()
        
        # 선택된 파일 경로 저장
        self.selected_frames = [Path(item.data(Qt.UserRole)) for item in selected_items]
        
        # 선택 상태 업데이트
        self.selection_label.setText(f"Selected: {selected_count}/{self.SELECT_COUNT}")
        
        # 선택된 사진을 미리보기 영역에 표시
        for i, label in enumerate(self.selected_preview_labels):
            if i < selected_count:
                # 선택된 사진 로드 및 표시
                img_path = self.selected_frames[i]
                if img_path.exists():
                    try:
                        pixmap = QPixmap(str(img_path))
                        if not pixmap.isNull():
                            # 레이블 크기에 맞춰 스케일링
                            scaled = pixmap.scaled(
                                label.width(),
                                label.height(),
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation,
                            )
                            label.setPixmap(scaled)
                            label.setText("")
                        else:
                            label.setText(f"Photo {i+1}\n(Invalid image)")
                    except Exception as e:
                        label.setText(f"Photo {i+1}\n(Error)")
                        print(f"미리보기 로드 오류: {e}")
                else:
                    label.setText(f"Photo {i+1}\n(Not found)")
            else:
                # 빈 슬롯
                label.clear()
                label.setText(f"Photo {i+1}")
        
        # 3장이 선택되면 완료 버튼 활성화
        if selected_count == self.SELECT_COUNT:
            self.finalize_button.setEnabled(True)
            self.finalize_button.setText("✓ Complete Selection - View Final Result!")
            self.finalize_button.setStyleSheet(
                "padding: 15px 30px; "
                "font-size: 18px; "
                "font-weight: bold; "
                "background-color: #4CAF50; "
                "color: white; "
                "border-radius: 5px;"
            )
            self.selection_label.setText(f"✓ {self.SELECT_COUNT} photos selected! Click button below to view result")
        else:
            self.finalize_button.setEnabled(False)
            self.finalize_button.setText(f"Complete Selection ({selected_count}/{self.SELECT_COUNT} Photos)")
            self.finalize_button.setStyleSheet(
                "padding: 15px 30px; "
                "font-size: 18px; "
                "font-weight: bold; "
                "background-color: #9E9E9E; "
                "color: white; "
                "border-radius: 5px;"
            )

    def finalize_selection(self):
        """선택 완료 버튼 클릭 시 호출되는 핸들러."""
        if len(self.selected_frames) != self.SELECT_COUNT:
            self.status_label.setText("Please select 3 photos")
            return
        
        # 선택된 3장의 파일 경로 출력
        self.status_label.setText("Processing...")
        print(f"Selected {self.SELECT_COUNT} photos:")
        for i, path in enumerate(self.selected_frames, 1):
            print(f"  {i}. {path}")
        
        # 최종 결과 화면 열기
        result_dialog = FinalResultDialog(self.selected_frames, self.output_dir, self)
        result_dialog.exec_()
        
        self.status_label.setText("Final selection complete!")

    # ---- Qt lifecycle -------------------------------------------------------------

    def closeEvent(self, event):
        if self.timer_stream.isActive():
            self.timer_stream.stop()
        if self.timer_countdown.isActive():
            self.timer_countdown.stop()

        if self.capture.isOpened():
            self.capture.release()
        cv2.destroyAllWindows()
        super().closeEvent(event)


class FinalResultDialog(QDialog):
    """최종 결과를 표시하고 다운로드할 수 있는 다이얼로그."""
    
    def __init__(self, selected_frames: List[Path], output_dir: Path, parent=None):
        super().__init__(parent)
        self.selected_frames = selected_frames
        self.output_dir = output_dir
        self.combined_image_path = None
        
        self.setWindowTitle("Final Result - 3-Cut Photo Booth")
        self.resize(1000, 700)
        
        self.init_ui()
        self.create_combined_image()
    
    def init_ui(self):
        """UI 초기화."""
        layout = QVBoxLayout(self)
        
        # 제목
        title_label = QLabel("Your 3-Cut Photo", self)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; padding: 20px;")
        layout.addWidget(title_label)
        
        # 합성된 이미지 표시 영역
        self.result_label = QLabel("Processing...", self)
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setMinimumSize(800, 500)
        self.result_label.setStyleSheet(
            "border: 2px solid #ccc; "
            "background-color: #f0f0f0; "
            "color: #999;"
        )
        layout.addWidget(self.result_label)
        
        # 버튼 영역
        button_layout = QHBoxLayout()
        
        self.download_button = QPushButton("Download", self)
        self.download_button.setStyleSheet(
            "padding: 12px 24px; "
            "font-size: 18px; "
            "background-color: #2196F3; "
            "color: white;"
        )
        self.download_button.clicked.connect(self.download_image)
        self.download_button.setEnabled(False)
        
        self.close_button = QPushButton("Close", self)
        self.close_button.setStyleSheet(
            "padding: 12px 24px; "
            "font-size: 18px; "
            "background-color: #757575; "
            "color: white;"
        )
        self.close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)
    
    def create_combined_image(self):
        """3장의 이미지를 합성합니다."""
        try:
            # 출력 파일 경로 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.combined_image_path = self.output_dir / f"final_result_{timestamp}.png"
            
            # 이미지 합성
            success = combine_three_images(
                self.selected_frames,
                self.combined_image_path,
                layout="vertical"
            )
            
            if success and self.combined_image_path.exists():
                # 합성된 이미지 표시
                pixmap = QPixmap(str(self.combined_image_path))
                scaled = pixmap.scaled(
                    self.result_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.result_label.setPixmap(scaled)
                self.result_label.setText("")
                self.download_button.setEnabled(True)
            else:
                self.result_label.setText("Failed to create combined image")
        
        except Exception as e:
            self.result_label.setText(f"Error: {str(e)}")
            print(f"이미지 합성 오류: {e}")
    
    def download_image(self):
        """이미지를 다운로드합니다."""
        if self.combined_image_path is None or not self.combined_image_path.exists():
            return
        
        # 파일 다이얼로그 열기
        default_filename = f"3cut_photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Image",
            str(Path.home() / "Downloads" / default_filename),
            "PNG Images (*.png);;All Files (*)"
        )
        
        if file_path:
            try:
                # 파일 복사
                import shutil
                shutil.copy2(self.combined_image_path, file_path)
                self.result_label.setText(f"Image saved to:\n{file_path}")
            except Exception as e:
                self.result_label.setText(f"Failed to save image: {str(e)}")
                print(f"파일 저장 오류: {e}")


def main():
    app = QApplication(sys.argv)
    window = PhotoBoothWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()