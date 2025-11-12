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
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
    THUMBNAIL_WIDTH = 350  # 갤러리 썸네일 너비 (2열 그리드에 맞춤)
    THUMBNAIL_HEIGHT = 200  # 갤러리 썸네일 최대 높이 (더 작게 설정)

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
        self.gallery_labels = []  # 갤러리 썸네일 레이블들
        self.gallery_label_to_file = {}  # 레이블에서 파일 경로로 매핑
        self.gallery_label_size = {}  # 레이블의 원본 크기 저장 (width, height)
        self.selected_gallery_labels = []  # 선택된 갤러리 레이블들

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
        
        # 상단: 전체 갤러리 (2x4 그리드)
        gallery_top = QWidget(self)
        
        # 스크롤 영역 생성
        self.gallery_scroll = QScrollArea(self)
        self.gallery_scroll.setWidgetResizable(True)  # 그리드 위젯이 자동으로 크기 조정
        self.gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.gallery_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # 그리드 컨테이너 위젯
        self.gallery_grid_widget = QWidget(self)
        self.gallery_grid = QGridLayout(self.gallery_grid_widget)
        self.gallery_grid.setContentsMargins(10, 10, 10, 10)  
        self.gallery_grid.setSpacing(10)  # 아이템 간격 없음
        # 2열 균등 분배 (정확히 50:50)
        self.gallery_grid.setColumnStretch(0, 1)
        self.gallery_grid.setColumnStretch(1, 1)
        self.gallery_grid.setColumnMinimumWidth(0, 0)
        self.gallery_grid.setColumnMinimumWidth(1, 0)
        # 4행 설정 (초기 최소 높이 설정)
        INITIAL_MIN_HEIGHT = 100 # 초기값, 동적으로 덮어씌워질 예정
        for i in range(4):
            self.gallery_grid.setRowMinimumHeight(i, INITIAL_MIN_HEIGHT)
            self.gallery_grid.setRowStretch(i, 0)  # 고정 높이이므로 stretch 제거
        
        # 그리드 위젯 크기 정책 설정
        # 너비는 스크롤 영역에 맞춰지고, 높이는 고정 (4행 × THUMBNAIL_HEIGHT)
        self.gallery_grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 그리드 위젯의 최소/최대 높이 설정 (INITIAL_MIN_HEIGHT 사용)
        grid_height = 4 * INITIAL_MIN_HEIGHT
        self.gallery_grid_widget.setMinimumHeight(grid_height)
        self.gallery_grid_widget.setMaximumHeight(grid_height)
        
        self.gallery_scroll.setWidget(self.gallery_grid_widget)
        
        # 그리드 위젯 너비를 viewport 너비에 맞추는 함수 (높이 동적 계산 추가)
        def update_grid_width():
            if hasattr(self, 'gallery_scroll') and hasattr(self, 'gallery_grid_widget'):
                viewport_width = self.gallery_scroll.viewport().width()
                if viewport_width > 0:

                    # 1. 여백 및 마진 값 가져오기
                    grid_spacing = self.gallery_grid.spacing() # 10px
                    # 좌우 마진 합계
                    grid_margin = (self.gallery_grid.contentsMargins().left() + 
                                   self.gallery_grid.contentsMargins().right())

                    # 2. 썸네일 너비 계산 (뷰포트 너비의 절반)
                    # 유효 너비 = 뷰포트 너비 - 좌우 마진 - 2개 열 사이 간격 1개
                    effective_content_width = viewport_width - grid_margin - grid_spacing
                    thumbnail_width = effective_content_width / 2

                    # 3. 썸네일 높이 계산 (최종 사진 비율 3:4 적용)
                    THUMBNAIL_ASPECT_RATIO = 3 / 4
                    new_thumbnail_height = int(thumbnail_width * THUMBNAIL_ASPECT_RATIO)

                    # 4. 갤러리 그리드 행 높이 업데이트
                    for i in range(4):
                        self.gallery_grid.setRowMinimumHeight(i, new_thumbnail_height)
                    
                    # 5. 갤러리 위젯의 고정 높이 업데이트 (4행 기준)
                    # 높이 = (4행 * 높이) + (3개 행 사이 간격) + (상하 마진)
                    grid_height = 4 * new_thumbnail_height + (3 * grid_spacing)+ (self.gallery_grid.contentsMargins().top() + self.gallery_grid.contentsMargins().bottom())
                    self.gallery_grid_widget.setMinimumHeight(grid_height)
                    self.gallery_grid_widget.setMaximumHeight(grid_height)

                    # 6. 그리드 위젯의 최대 너비를 설정
                    self.gallery_grid_widget.setMaximumWidth(viewport_width)
                    self.gallery_grid_widget.updateGeometry()
                    
                    # 7. 갤러리 내 썸네일 위젯 크기 업데이트
                    if hasattr(self, 'update_thumbnails_size'):
                        self.update_thumbnails_size(new_thumbnail_height, int(thumbnail_width))

        # 그리드 너비 업데이트 함수 저장 (resizeEvent에서 사용)
        self._update_grid_width_func = update_grid_width
        
        # 초기 크기 설정 (창이 표시된 후)
        QTimer.singleShot(100, update_grid_width)

        # 선택 상태 표시 레이블
        self.selection_label = QLabel("Select photos (0/3)", self)
        self.selection_label.setAlignment(Qt.AlignCenter)
        self.selection_label.setStyleSheet("font-size: 16px; padding: 8px;")

        gallery_top_layout = QVBoxLayout(gallery_top)
        gallery_top_layout.setContentsMargins(5, 5, 5, 5)
        gallery_top_layout.addWidget(QLabel("Captured Photos (Select 3 of 8)", self))
        gallery_top_layout.addWidget(self.gallery_scroll, stretch=1)
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
        self.selected_gallery_labels = []
        
        # 갤러리 그리드 초기화
        for label in self.gallery_labels:
            self.gallery_grid.removeWidget(label)
            label.deleteLater()
        self.gallery_labels.clear()
        self.gallery_label_to_file.clear()
        self.gallery_label_size.clear()  # 크기 정보도 초기화
        
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
            
            # 그리드 위치 계산 (2열, 4행)
            index = len(self.captured_frames) - 1  # 0부터 시작
            row = index // 2  # 행 (0, 1, 2, 3)
            col = index % 2   # 열 (0, 1)
            
            # 썸네일 레이블 생성
            thumb_label = QLabel(self.gallery_grid_widget)  # 부모를 그리드 위젯으로 설정
            thumb_label.setAlignment(Qt.AlignCenter)
            # 이미지가 레이블 크기에 맞춰 확장 (그리드 셀을 완전히 채움)
            thumb_label.setScaledContents(True)
            # 크기 정책을 Fixed로 설정 (크기 변경 완전 방지)
            thumb_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            # 4:3 비율로 크기 계산 (높이 기준)
            thumb_height = self.THUMBNAIL_HEIGHT
            thumb_width = int(thumb_height * 4 / 3)  # 4:3 비율
            
            # viewport 너비 제한 확인 (2열이므로 각 썸네일은 viewport 너비의 절반을 넘지 않아야 함)
            viewport_width = self.gallery_scroll.viewport().width() if hasattr(self, 'gallery_scroll') else 400
            if viewport_width <= 0:
                viewport_width = self.gallery_scroll.width() if hasattr(self, 'gallery_scroll') else 400
                if viewport_width <= 0:
                    viewport_width = 400
            
            max_width = viewport_width // 2
            # 계산된 너비가 최대 너비를 초과하면 높이를 조정
            if thumb_width > max_width:
                thumb_width = max_width
                thumb_height = int(thumb_width * 3 / 4)  # 4:3 비율 유지 (너비 기준)
            
            thumb_label.setFixedSize(thumb_width, thumb_height)  # 4:3 비율 고정 크기
            # 레이블의 원본 크기 저장 (선택 시 크기 변경 방지)
            self.gallery_label_size[thumb_label] = (thumb_width, thumb_height)
            thumb_label.setStyleSheet(
                "QLabel { "
                "border: 2px solid transparent; "
                "background-color: #f0f0f0; "
                "width: " + str(thumb_width) + "px; "
                "height: " + str(thumb_height) + "px; "
                "min-width: " + str(thumb_width) + "px; "
                "max-width: " + str(thumb_width) + "px; "
                "min-height: " + str(thumb_height) + "px; "
                "max-height: " + str(thumb_height) + "px; "
                "}"
                "QLabel:hover { "
                "border: 3px solid #2196F3; "
                "}"
            )
            thumb_label.setCursor(Qt.PointingHandCursor)  # 클릭 가능 커서
            
            # 레이블 클릭 이벤트 연결 (클로저 문제 방지를 위해 기본 인자 사용)
            def make_click_handler(label):
                return lambda event: self.on_gallery_label_clicked(label)
            thumb_label.mousePressEvent = make_click_handler(thumb_label)
            
            # 파일 경로 매핑 저장
            self.gallery_label_to_file[thumb_label] = filename
            
            # 썸네일 생성 - 그리드 셀 크기에 맞게 스케일링
            # viewport 너비의 절반과 THUMBNAIL_HEIGHT를 기준으로 크기 계산
            if hasattr(self, 'gallery_scroll'):
                viewport_width = self.gallery_scroll.viewport().width()
                if viewport_width <= 0:
                    # viewport 너비가 0이면 스크롤 영역 너비 사용
                    viewport_width = self.gallery_scroll.width()
                    if viewport_width <= 0:
                        viewport_width = 400  # 기본값
            else:
                viewport_width = 400  # 기본값
            
            thumb_target_width = max(viewport_width // 2, 200)  # 최소 200px
            thumb_target_height = self.THUMBNAIL_HEIGHT
            
            # 원본 이미지 크기
            orig_height, orig_width = thumb_image.height(), thumb_image.width()
            
            # 비율 유지하면서 타겟 크기에 맞게 스케일링
            # 높이 기준으로 스케일링 (높이가 제한이므로)
            scale_height = thumb_target_height / orig_height
            scale_width = thumb_target_width / orig_width
            scale = min(scale_height, scale_width, 1.0)  # 확대하지 않고 축소만
            
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
            
            # 썸네일 생성
            thumb_pixmap = QPixmap.fromImage(thumb_image).scaled(
                new_width, new_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            
            if thumb_pixmap.isNull():
                print(f"Warning: Failed to create pixmap for {filename}")
                return
            
            # 썸네일을 레이블에 설정
            thumb_label.setPixmap(thumb_pixmap)
            
            # 그리드에 추가 (2열, 4행)
            self.gallery_grid.addWidget(thumb_label, row, col)
            self.gallery_labels.append(thumb_label)
            
            # 레이블이 보이도록 설정
            thumb_label.show()
            
            # 그리드 레이아웃 업데이트
            self.gallery_grid_widget.updateGeometry()
            
            # 디버깅: 아이템이 추가되었는지 확인
            print(f"Added item to gallery: {filename.name}, position: row={row}, col={col}, total items: {len(self.gallery_labels)}")
            if len(self.gallery_labels) == 1:
                # 첫 번째 썸네일 추가 시 그리드 너비 확인
                QTimer.singleShot(200, lambda: print(f"Grid widget size: {self.gallery_grid_widget.width()}x{self.gallery_grid_widget.height()}, Scroll viewport: {self.gallery_scroll.viewport().width()}"))

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

    
    def update_thumbnails_size(self, new_height, new_width):
        """
        갤러리 그리드 내의 모든 썸네일 위젯의 높이와 너비를 조정하고 이미지를 리스케일링합니다.
        """
        
        # 예시: QGridLayout을 순회하며 위젯 크기 조정
        for i in range(self.gallery_grid.count()):
            item = self.gallery_grid.itemAt(i)
            if item and item.widget():
                thumbnail_widget = item.widget() # 썸네일 위젯 (QLabel 등으로 가정)
                
                # 1. 썸네일 위젯의 높이를 설정합니다.
                thumbnail_widget.setFixedHeight(new_width,new_height) 
                
                # 2. 썸네일 위젯에 표시되는 이미지를 새 크기에 맞게 다시 스케일링합니다.
                # 이 로직은 썸네일 위젯이 원본 QPixmap을 저장하고 있을 때 작동합니다.
                if hasattr(thumbnail_widget, 'original_pixmap') and thumbnail_widget.original_pixmap is not None:
                    scaled_pixmap = thumbnail_widget.original_pixmap.scaled(
                        new_width,new_height, 
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    thumbnail_widget.setPixmap(scaled_pixmap)
                
                thumbnail_widget.update() # 위젯 강제 업데이트
    # ---- Selection handlers -------------------------------------------------------

    def on_gallery_label_clicked(self, label):
        """갤러리 레이블 클릭 시 호출되는 핸들러."""
        # 레이블에서 파일 경로 가져오기
        if label not in self.gallery_label_to_file:
            return
        
        # 이미 선택된 레이블인지 확인
        if label in self.selected_gallery_labels:
            # 선택 해제 - 스타일만 변경, 크기는 변경하지 않음
            self.selected_gallery_labels.remove(label)
            # 저장된 원본 크기 사용 (크기 변경 방지)
            if label in self.gallery_label_size:
                original_width, original_height = self.gallery_label_size[label]
            else:
                # 저장된 크기가 없으면 현재 크기 사용
                original_width = label.width()
                original_height = label.height()
                self.gallery_label_size[label] = (original_width, original_height)
            # 크기를 강제로 고정 (크기 변경 완전 방지)
            label.setFixedSize(original_width, original_height)
            # 크기 정책은 이미 Fixed로 설정되어 있으므로 변경하지 않음
            # 스타일만 변경하되 크기 속성도 포함 (크기 변경 방지)
            label.setStyleSheet(
                "QLabel { "
                "border: 2px solid transparent; "
                "background-color: #f0f0f0; "
                "width: " + str(original_width) + "px; "
                "height: " + str(original_height) + "px; "
                "min-width: " + str(original_width) + "px; "
                "max-width: " + str(original_width) + "px; "
                "min-height: " + str(original_height) + "px; "
                "max-height: " + str(original_height) + "px; "
                "}"
                "QLabel:hover { "
                "border: 3px solid #2196F3; "
                "}"
            )
        else:
            # 선택 추가 (최대 3장까지만)
            if len(self.selected_gallery_labels) >= self.SELECT_COUNT:
                # 가장 오래된 선택 해제 - 스타일만 변경, 크기는 변경하지 않음
                oldest_label = self.selected_gallery_labels.pop(0)
                # 저장된 원본 크기 사용 (크기 변경 방지)
                if oldest_label in self.gallery_label_size:
                    old_width, old_height = self.gallery_label_size[oldest_label]
                else:
                    # 저장된 크기가 없으면 현재 크기 사용
                    old_width = oldest_label.width()
                    old_height = oldest_label.height()
                    self.gallery_label_size[oldest_label] = (old_width, old_height)
                # 크기를 강제로 고정 (크기 변경 완전 방지)
                oldest_label.setFixedSize(old_width, old_height)
                # 크기 정책은 이미 Fixed로 설정되어 있으므로 변경하지 않음
                # 스타일만 변경하되 크기 속성도 포함 (크기 변경 방지)
                oldest_label.setStyleSheet(
                    "QLabel { "
                    "border: 2px solid transparent; "
                    "background-color: #f0f0f0; "
                    "width: " + str(old_width) + "px; "
                    "height: " + str(old_height) + "px; "
                    "min-width: " + str(old_width) + "px; "
                    "max-width: " + str(old_width) + "px; "
                    "min-height: " + str(old_height) + "px; "
                    "max-height: " + str(old_height) + "px; "
                    "}"
                    "QLabel:hover { "
                    "border: 3px solid #2196F3; "
                    "}"
                )
            
            # 새 레이블 선택 - 스타일만 변경, 크기는 변경하지 않음
            self.selected_gallery_labels.append(label)
            # 저장된 원본 크기 사용 (크기 변경 방지)
            if label in self.gallery_label_size:
                original_width, original_height = self.gallery_label_size[label]
            else:
                # 저장된 크기가 없으면 현재 크기 사용
                original_width = label.width()
                original_height = label.height()
                self.gallery_label_size[label] = (original_width, original_height)
            # 크기를 강제로 고정 (크기 변경 완전 방지)
            label.setFixedSize(original_width, original_height)
            # 크기 정책은 이미 Fixed로 설정되어 있으므로 변경하지 않음
            # 스타일만 변경하되 크기 속성도 포함 (크기 변경 방지)
            # 선택 시 테두리 색깔만 변경 (border 크기는 2px로 유지하여 크기 변경 방지)
            # 모든 상태에서 테두리 색상이 명확하게 변경되도록 설정
            label.setStyleSheet(
                "QLabel { "
                "border: 2px solid #4CAF50; "
                "background-color: rgba(76, 175, 80, 0.1); "
                "width: " + str(original_width) + "px; "
                "height: " + str(original_height) + "px; "
                "min-width: " + str(original_width) + "px; "
                "max-width: " + str(original_width) + "px; "
                "min-height: " + str(original_height) + "px; "
                "max-height: " + str(original_height) + "px; "
                "}"
                "QLabel:hover { "
                "border: 2px solid #66BB6A; "
                "background-color: rgba(76, 175, 80, 0.25); "
                "}"
            )
        
        # 선택된 파일 경로 업데이트
        self.selected_frames = [self.gallery_label_to_file[label] for label in self.selected_gallery_labels]
        selected_count = len(self.selected_gallery_labels)
        
        # 선택 상태 업데이트
        self.selection_label.setText(f"Selected: {selected_count}/{self.SELECT_COUNT}")
        
        # 선택된 사진을 미리보기 영역에 표시
        for i, preview_label in enumerate(self.selected_preview_labels):
            if i < selected_count:
                # 선택된 사진 로드 및 표시
                img_path = self.selected_frames[i]
                if img_path.exists():
                    try:
                        pixmap = QPixmap(str(img_path))
                        if not pixmap.isNull():
                            # 레이블 크기에 맞춰 스케일링
                            scaled = pixmap.scaled(
                                preview_label.width(),
                                preview_label.height(),
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation,
                            )
                            preview_label.setPixmap(scaled)
                            preview_label.setText("")
                        else:
                            preview_label.setText(f"Photo {i+1}\n(Invalid image)")
                    except Exception as e:
                        preview_label.setText(f"Photo {i+1}\n(Error)")
                        print(f"미리보기 로드 오류: {e}")
                else:
                    preview_label.setText(f"Photo {i+1}\n(Not found)")
            else:
                # 빈 슬롯
                preview_label.clear()
                preview_label.setText(f"Photo {i+1}")
        
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

    def resizeEvent(self, event):
        """창 크기가 변경될 때 호출됩니다."""
        super().resizeEvent(event)
        # 그리드 너비 업데이트 (창 크기 변경 시)
        if hasattr(self, '_update_grid_width_func'):
            # 약간의 지연을 두어 레이아웃이 완전히 업데이트된 후 실행
            QTimer.singleShot(50, self._update_grid_width_func)

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