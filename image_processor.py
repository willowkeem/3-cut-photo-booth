"""Image processing utilities.

Helper functions to transform frames before saving or displaying.
"""
from pathlib import Path
from typing import List

import cv2
import numpy as np


def combine_three_images(image_paths: List[Path], output_path: Path, layout: str = "vertical") -> bool:
    """3장의 이미지를 합성하여 하나의 이미지로 만듭니다.
    
    Args:
        image_paths: 합성할 이미지 파일 경로 리스트 (3장)
        output_path: 출력 파일 경로
        layout: 배치 방식 ("vertical" 또는 "horizontal")
    
    Returns:
        성공 여부
    """
    if len(image_paths) != 3:
        raise ValueError("정확히 3장의 이미지가 필요합니다.")
    
    try:
        # 이미지 로드
        images = []
        for img_path in image_paths:
            if not img_path.exists():
                raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {img_path}")
            
            img = cv2.imread(str(img_path))
            if img is None:
                raise ValueError(f"이미지를 로드할 수 없습니다: {img_path}")
            
            images.append(img)
        
        # 모든 이미지를 같은 너비로 리사이즈 (세로 배치의 경우)
        if layout == "vertical":
            # 가장 넓은 이미지의 너비에 맞춤
            max_width = max(img.shape[1] for img in images)
            resized_images = []
            for img in images:
                height = int(img.shape[0] * (max_width / img.shape[1]))
                resized = cv2.resize(img, (max_width, height), interpolation=cv2.INTER_LANCZOS4)
                resized_images.append(resized)
            
            # 세로로 연결
            combined = np.vstack(resized_images)
        
        elif layout == "horizontal":
            # 가장 높은 이미지의 높이에 맞춤
            max_height = max(img.shape[0] for img in images)
            resized_images = []
            for img in images:
                width = int(img.shape[1] * (max_height / img.shape[0]))
                resized = cv2.resize(img, (width, max_height), interpolation=cv2.INTER_LANCZOS4)
                resized_images.append(resized)
            
            # 가로로 연결
            combined = np.hstack(resized_images)
        
        else:
            raise ValueError("layout은 'vertical' 또는 'horizontal'이어야 합니다.")
        
        # 결과 저장
        output_path.parent.mkdir(parents=True, exist_ok=True)
        success = cv2.imwrite(str(output_path), combined)
        
        return success
    
    except Exception as e:
        print(f"이미지 합성 오류: {e}")
        return False


def add_frame_to_image(image_path: Path, frame_path: Path, output_path: Path) -> bool:
    """이미지에 프레임을 추가합니다.
    
    Args:
        image_path: 원본 이미지 경로
        frame_path: 프레임 이미지 경로
        output_path: 출력 파일 경로
    
    Returns:
        성공 여부
    """
    try:
        # 이미지와 프레임 로드
        img = cv2.imread(str(image_path))
        frame = cv2.imread(str(frame_path), cv2.IMREAD_UNCHANGED)
        
        if img is None or frame is None:
            return False
        
        # 프레임이 투명도 채널이 있는 경우 (RGBA)
        if frame.shape[2] == 4:
            # 알파 채널을 마스크로 사용
            alpha = frame[:, :, 3] / 255.0
            frame_rgb = frame[:, :, :3]
            
            # 이미지와 프레임 크기 맞추기
            if img.shape[:2] != frame.shape[:2]:
                frame_rgb = cv2.resize(frame_rgb, (img.shape[1], img.shape[0]))
                alpha = cv2.resize(alpha, (img.shape[1], img.shape[0]))
            
            # alpha를 3차원으로 확장 (채널 차원 추가)
            if len(alpha.shape) == 2:
                alpha = alpha[:, :, np.newaxis]
            
            # 블렌딩
            result = (img * (1 - alpha) + frame_rgb * alpha).astype(np.uint8)
        else:
            # 투명도가 없는 경우 단순 오버레이
            if img.shape[:2] != frame.shape[:2]:
                frame = cv2.resize(frame, (img.shape[1], img.shape[0]))
            
            result = cv2.addWeighted(img, 0.7, frame, 0.3, 0)
        
        # 결과 저장
        output_path.parent.mkdir(parents=True, exist_ok=True)
        success = cv2.imwrite(str(output_path), result)
        
        return success
    
    except Exception as e:
        print(f"프레임 추가 오류: {e}")
        return False
