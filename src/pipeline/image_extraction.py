"""
Image extraction from lecture slides using computer vision.

Extracts figures, diagrams, and images from slide frames using traditional
CV techniques (edge detection, contour finding) with optional text exclusion.
"""

import asyncio
import io
import logging
import os
from dataclasses import asdict, dataclass

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class DetectedRegion:
    """A detected image region within a slide."""

    label: str
    confidence: float
    xmin: int
    ymin: int
    xmax: int
    ymax: int

    @property
    def area(self) -> int:
        return (self.xmax - self.xmin) * (self.ymax - self.ymin)

    @property
    def width(self) -> int:
        return self.xmax - self.xmin

    @property
    def height(self) -> int:
        return self.ymax - self.ymin

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractedImage:
    """An extracted image with metadata."""

    slide_index: int
    region_index: int
    label: str
    confidence: float
    bbox: dict  # {xmin, ymin, xmax, ymax}
    width: int
    height: int
    path: str  # Local or S3 path to the extracted image
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExtractedImage":
        return cls(**data)


def detect_images_opencv(
    image_path: str,
    min_area_ratio: float = 0.01,
    max_area_ratio: float = 0.8,
    use_text_exclusion: bool = False,
) -> list[DetectedRegion]:
    """
    Detect figure/image regions using traditional CV techniques.

    Uses edge detection and contour finding to identify image regions.
    Optionally excludes text regions using EasyOCR (if installed).

    Args:
        image_path: Path to the slide image
        min_area_ratio: Minimum region area as fraction of total image area
        max_area_ratio: Maximum region area as fraction of total image area
        use_text_exclusion: Whether to use OCR to exclude text regions

    Returns:
        List of detected image regions
    """
    img = cv2.imread(image_path)
    if img is None:
        logger.warning(f"Could not read image: {image_path}")
        return []

    h, w = img.shape[:2]
    total_area = h * w
    min_area = int(total_area * min_area_ratio)
    max_area = int(total_area * max_area_ratio)

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Create text mask if exclusion is enabled
    text_mask = np.zeros((h, w), dtype=np.uint8)
    if use_text_exclusion:
        try:
            import easyocr

            reader = easyocr.Reader(["en"], verbose=False)
            results = reader.readtext(image_path)
            for bbox, _text, _prob in results:
                pts = np.array(bbox, dtype=np.int32)
                cv2.fillPoly(text_mask, [pts], 255)
            # Dilate text regions slightly to create buffer
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
            text_mask = cv2.dilate(text_mask, kernel, iterations=1)
        except ImportError:
            logger.debug("EasyOCR not installed, skipping text exclusion")

    # Edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 30, 100)

    # Dilate edges to connect nearby contours
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area < area < max_area:
            x, y, bw, bh = cv2.boundingRect(cnt)

            # Filter by aspect ratio (exclude very thin/wide regions)
            aspect_ratio = bw / float(bh) if bh > 0 else 0
            if 0.2 < aspect_ratio < 5.0:
                # Check text overlap if exclusion enabled
                if use_text_exclusion:
                    roi_mask = text_mask[y : y + bh, x : x + bw]
                    text_overlap = np.sum(roi_mask > 0) / (bw * bh)
                    if text_overlap > 0.3:  # More than 30% text, skip
                        continue

                # Calculate confidence score based on area and shape
                area_score = min(1.0, area / (total_area * 0.1))
                aspect_score = 1.0 - abs(1.0 - aspect_ratio) / 4.0
                confidence = (area_score + aspect_score) / 2

                regions.append(
                    DetectedRegion(
                        label="figure",
                        confidence=confidence,
                        xmin=x,
                        ymin=y,
                        xmax=x + bw,
                        ymax=y + bh,
                    )
                )

    # Sort by confidence (highest first)
    regions.sort(key=lambda r: r.confidence, reverse=True)
    return regions


def crop_region(
    image_path: str,
    region: DetectedRegion,
    padding: int = 5,
) -> tuple[Image.Image, int, int]:
    """
    Crop a region from an image.

    Args:
        image_path: Path to the source image
        region: Region to crop
        padding: Padding to add around the region

    Returns:
        Tuple of (cropped PIL Image, width, height)
    """
    img = Image.open(image_path)
    w, h = img.size

    # Apply padding (clamped to image bounds)
    x1 = max(0, region.xmin - padding)
    y1 = max(0, region.ymin - padding)
    x2 = min(w, region.xmax + padding)
    y2 = min(h, region.ymax + padding)

    cropped = img.crop((x1, y1, x2, y2))
    return cropped, x2 - x1, y2 - y1


def compress_image(
    image: Image.Image,
    max_size_kb: int = 200,
    min_quality: int = 40,
    max_dimension: int = 800,
) -> tuple[bytes, int]:
    """
    Compress an image to reduce file size while maintaining quality.

    Args:
        image: PIL Image to compress
        max_size_kb: Target maximum size in KB
        min_quality: Minimum JPEG quality to try
        max_dimension: Maximum dimension (width or height)

    Returns:
        Tuple of (compressed image bytes, final size in bytes)
    """
    # Convert to RGB if necessary (for JPEG)
    if image.mode in ("RGBA", "P"):
        background = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "RGBA":
            background.paste(image, mask=image.split()[3])
        else:
            background.paste(image)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    # Resize if larger than max dimension
    w, h = image.size
    if max(w, h) > max_dimension:
        ratio = max_dimension / max(w, h)
        new_size = (int(w * ratio), int(h * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    # Binary search for optimal quality
    max_size_bytes = max_size_kb * 1024
    quality = 85

    while quality >= min_quality:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        size = buffer.tell()

        if size <= max_size_bytes:
            return buffer.getvalue(), size

        quality -= 10

    # Return at minimum quality if we can't hit target
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=min_quality, optimize=True)
    return buffer.getvalue(), buffer.tell()


async def extract_images_from_slide(
    slide_path: str,
    slide_index: int,
    output_dir: str,
    min_area_ratio: float = 0.02,
    max_area_ratio: float = 0.7,
    max_images_per_slide: int = 5,
    max_size_kb: int = 200,
) -> list[ExtractedImage]:
    """
    Extract images from a single slide.

    Args:
        slide_path: Path to the slide image
        slide_index: Index of the slide (for naming)
        output_dir: Directory to save extracted images
        min_area_ratio: Minimum region area as fraction of total
        max_area_ratio: Maximum region area as fraction of total
        max_images_per_slide: Maximum number of images to extract per slide
        max_size_kb: Target max size per image in KB

    Returns:
        List of ExtractedImage objects
    """
    os.makedirs(output_dir, exist_ok=True)

    # Detect image regions
    regions = await asyncio.to_thread(
        detect_images_opencv,
        slide_path,
        min_area_ratio,
        max_area_ratio,
        use_text_exclusion=False,  # Skip for performance
    )

    # Limit number of images per slide
    regions = regions[:max_images_per_slide]

    extracted = []
    for region_idx, region in enumerate(regions):
        try:
            # Crop the region
            cropped, width, height = await asyncio.to_thread(crop_region, slide_path, region)

            # Compress the image
            img_bytes, size_bytes = await asyncio.to_thread(compress_image, cropped, max_size_kb)

            # Save to file
            filename = f"slide{slide_index:03d}_img{region_idx:02d}.jpg"
            output_path = os.path.join(output_dir, filename)

            with open(output_path, "wb") as f:
                f.write(img_bytes)

            extracted.append(
                ExtractedImage(
                    slide_index=slide_index,
                    region_index=region_idx,
                    label=region.label,
                    confidence=region.confidence,
                    bbox={
                        "xmin": region.xmin,
                        "ymin": region.ymin,
                        "xmax": region.xmax,
                        "ymax": region.ymax,
                    },
                    width=width,
                    height=height,
                    path=output_path,
                    size_bytes=size_bytes,
                )
            )
        except Exception as e:
            logger.warning(f"Failed to extract region {region_idx} from slide {slide_index}: {e}")
            continue

    return extracted


def filter_images_by_size(
    images: list[ExtractedImage],
    max_total_mb: float = 45.0,
) -> list[ExtractedImage]:
    """
    Filter images to stay under a total size limit.

    Prioritizes images with higher confidence scores.

    Args:
        images: List of extracted images
        max_total_mb: Maximum total size in MB

    Returns:
        Filtered list of images
    """
    # Sort by confidence (highest first)
    sorted_images = sorted(images, key=lambda x: x.confidence, reverse=True)

    max_total_bytes = int(max_total_mb * 1024 * 1024)
    total_bytes = 0
    filtered = []

    for img in sorted_images:
        if total_bytes + img.size_bytes <= max_total_bytes:
            filtered.append(img)
            total_bytes += img.size_bytes
        else:
            logger.info(
                f"Excluding image {img.path} ({img.size_bytes / 1024:.1f}KB) - "
                f"would exceed {max_total_mb}MB limit"
            )

    return filtered
