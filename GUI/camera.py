"""
camera.py — Camera capture thread and raw image processing.
"""

import numpy as np
import cv2

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage


# ---------------------------------------------------------------------------
# Raw Bayer processing
# ---------------------------------------------------------------------------

def process_raw(
    input_array,
    R=False, G=False, G1=False, G2=False, B=False,
    RGB=True, RGB2=False,
    rgb_or_bgr=True,
    mono=False,
):
    """Demosaic a raw Bayer array captured from the Pi camera.

    By default returns an RGB stack. Pass a single channel flag (R/G/B/G1/G2)
    to extract just that colour plane, or RGB2 for a 2×2 tiled layout.
    """
    if "uint16" not in str(input_array.dtype):
        input_array = input_array.view(np.uint16)
        if mono:
            return input_array

    # Only one output mode at a time; channel flags override RGB.
    if R or G or B or G1 or G2 or RGB2:
        RGB = False

    if RGB:
        blue   = input_array[0::2, 0::2]
        red    = input_array[1::2, 1::2]
        green1 = input_array[0::2, 1::2]
        green2 = input_array[1::2, 0::2]
        green  = ((green1 & green2) + (green1 ^ green2) / 2).astype(np.uint16)
        channels = [red, green, blue] if rgb_or_bgr else [blue, green, red]
        return np.asarray(channels).transpose(1, 2, 0)

    if R:
        return input_array[1::2, 1::2]

    if G:
        green1 = input_array[0::2, 1::2]
        green2 = input_array[1::2, 0::2]
        return ((green1 & green2) + (green1 ^ green2) / 2).astype(np.uint16)

    if G1:
        return input_array[0::2, 1::2]

    if G2:
        return input_array[1::2, 0::2]

    if B:
        return input_array[0::2, 0::2]

    if RGB2:
        blue   = input_array[0::2, 0::2]
        red    = input_array[1::2, 1::2]
        green1 = input_array[0::2, 1::2]
        green2 = input_array[1::2, 0::2]
        top    = np.concatenate((red,    green1), axis=0)
        bottom = np.concatenate((green2, blue),   axis=0)
        return np.concatenate((top, bottom), axis=1)


# ---------------------------------------------------------------------------
# Camera capture thread
# ---------------------------------------------------------------------------

class CameraWorker(QThread):
    """Runs the Pi camera in a background thread and emits QImage frames."""

    frame_ready = pyqtSignal(QImage)

    # Camera configuration constants
    MAIN_FORMAT  = "XBGR8888"
    MAIN_SIZE    = (480, 360)
    RAW_FORMAT   = "SRGGB12"
    RAW_SIZE     = (4056, 3040)

    def __init__(self):
        super().__init__()
        self.running = True
        self._init_camera()

    def _init_camera(self):
        from picamera2 import Picamera2

        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"format": self.MAIN_FORMAT, "size": self.MAIN_SIZE},
            raw={"format": self.RAW_FORMAT,   "size": self.RAW_SIZE},
            display="main",
            queue=False,
            buffer_count=4,
        )
        self.picam2.configure(config)
        self.picam2.start()

    def run(self):
        while self.running:
            frame = self.picam2.capture_array("main")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = frame.shape
            qt_image = QImage(
                frame.data, w, h, ch * w, QImage.Format.Format_RGB888
            ).copy()

            self.frame_ready.emit(qt_image)

    def stop(self):
        self.running = False
        try:
            self.picam2.stop()
        except Exception:
            pass
        self.quit()
        self.wait()