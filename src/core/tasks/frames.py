"""
Frame extraction and comparison utilities.
"""

import cv2

from .config import FRAME_SCALE_FACTOR


def compare_frames_edges(frame1_gs, frame2_gs) -> float:
    """Edge-based frame comparison optimized for lecture slides.

    Uses Canny edge detection + normalized correlation.
    Works well for slides with similar colors but different text/content.
    Returns a value from 0 to 1, where 1 means identical.
    """
    # Apply Canny edge detection
    edges1 = cv2.Canny(frame1_gs, 50, 150)
    edges2 = cv2.Canny(frame2_gs, 50, 150)

    # Compute normalized cross-correlation
    # Flatten arrays for comparison
    e1 = edges1.flatten().astype(float)
    e2 = edges2.flatten().astype(float)

    # Normalize
    e1_norm = e1 - e1.mean()
    e2_norm = e2 - e2.mean()

    # Compute correlation
    numerator = (e1_norm * e2_norm).sum()
    denominator = ((e1_norm**2).sum() * (e2_norm**2).sum()) ** 0.5

    if denominator == 0:
        return 1.0 if (e1 == e2).all() else 0.0

    return max(0.0, numerator / denominator)


def preprocess_frame_for_comparison(frame, scale_factor: float = FRAME_SCALE_FACTOR):
    """Preprocess a frame for comparison.

    Args:
        frame: BGR frame from cv2
        scale_factor: Scale factor for resizing (0.25-1.0)

    Returns:
        Grayscale, downscaled frame ready for comparison
    """
    frame_small = cv2.resize(frame, None, fx=scale_factor, fy=scale_factor)
    return cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
