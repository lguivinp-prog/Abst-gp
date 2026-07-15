import os
import cv2
import numpy as np
from pdf2image import convert_from_path
from typing import List, Dict, Any

class ImagePreprocessor:
    def __init__(self, base_output_dir: str = "/data/processed"):
        self.base_output_dir = base_output_dir

    def deskew_image(self, image: np.ndarray) -> np.ndarray:
        """
        Uses Hough transform to detect text lines and compute the skew angle.
        Rotates the image to correct the skew.
        """
        # Convert to grayscale and apply Canny edge detection
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        # Detect lines using Hough transform
        lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
        
        if lines is None:
            return image
            
        angles = []
        for line in lines:
            rho, theta = line[0]
            # Convert theta to degrees
            angle = (theta * 180) / np.pi
            # Adjust angle to be between -45 and 45
            if angle > 45 and angle < 135:
                angle -= 90
            elif angle > 135:
                angle -= 180
            angles.append(angle)
            
        if not angles:
            return image
            
        # Get the median angle
        median_angle = np.median(angles)
        
        # Only deskew if the angle is significant but not too wild
        if abs(median_angle) < 0.5 or abs(median_angle) > 15:
            return image
            
        # Rotate the image
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        
        # Determine the new bounding box dimensions to avoid cropping
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        
        M[0, 2] += (new_w / 2) - center[0]
        M[1, 2] += (new_h / 2) - center[1]
        
        deskewed = cv2.warpAffine(image, M, (new_w, new_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return deskewed

    def process(self, document_id: str, pdf_path: str) -> Dict[str, Any]:
        original_dir = os.path.join(self.base_output_dir, str(document_id), "original")
        processed_dir = os.path.join(self.base_output_dir, str(document_id), "processed")
        
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(processed_dir, exist_ok=True)
        
        images = convert_from_path(pdf_path, dpi=300)
        
        processed_paths = []
        original_paths = []
        
        for idx, img in enumerate(images):
            page_name = f"page_{idx+1:03d}.png"
            orig_path = os.path.join(original_dir, page_name)
            proc_path = os.path.join(processed_dir, page_name)
            
            # Save original
            img.save(orig_path, "PNG")
            original_paths.append(orig_path)
            
            # Convert to cv2 format
            cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            
            # 1. Deskew
            deskewed_img = self.deskew_image(cv_img)
            
            # 2. Grayscale
            gray = cv2.cvtColor(deskewed_img, cv2.COLOR_BGR2GRAY)
            
            # 3. Adaptive Contrast / Thresholding
            # This is a gentle binarization to enhance text against background
            # We don't want to destroy faint text.
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5
            )
            
            # 4. Save processed image
            cv2.imwrite(proc_path, thresh)
            processed_paths.append(proc_path)
            
        return {
            "document_id": document_id,
            "total_pages": len(images),
            "original_images": original_paths,
            "processed_images": processed_paths
        }

    def detect_visual_noise(self, image_path: str) -> Dict[str, Any]:
        """
        Stub to detect stamps, signatures, or logos.
        Will not delete pixels, just identify regions for the layout engine.
        """
        # A simple implementation for the future could look for connected components
        # of unusual size or specific color masking (e.g., blue/red stamps).
        
        return {
            "possible_stamp": False,
            "areas": []
        }
