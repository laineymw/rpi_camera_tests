"""
ui.py — Main application window (ModernMainWindow).

Depends on: camera.py, cnc.py
"""

import math
import time
import datetime
import traceback
import sys
import os

import cv2
import numpy as np
import RPi.GPIO as GPIO

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QTextCursor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QApplication,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QLabel, QTextEdit,
    QPushButton, QCheckBox, QDoubleSpinBox,
    QSlider, QLineEdit, QSizePolicy, QInputDialog,
)

from camera import CameraWorker, process_raw
from cnc import CNCController, CNCWorker


# ---------------------------------------------------------------------------
# File-based debug logger — survives GUI crashes
# ---------------------------------------------------------------------------

DEBUG_LOG_PATH = "/home/r/rpi_camera_tests/debug.log"

def dlog(msg: str):
    """Write a timestamped debug line to file immediately (flush after every write)."""
    line = f"{time.strftime('%H:%M:%S')} [DEBUG] {msg}\n"
    print(line, end="")   # also goes to terminal if it's still open
    try:
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(line)
    except Exception:
        pass


# Catch any unhandled exception, log the full traceback, then re-raise
def _excepthook(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    dlog(f"UNHANDLED EXCEPTION:\n{msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SERIAL_PORT   = "/dev/ttyUSB0"
BAUD_RATE     = 115200
SETTINGS_PATH = "/home/r/rpi_camera_tests/camera_settings.txt"
LED_PIN       = 26
CENTER_POS    = {"x_pos": -81, "y_pos": -67, "z_pos": -17}

DARK_THEME = """
    QMainWindow { background-color: #1e1e2e; color: #ffffff; }
    QTextEdit {
        background-color: #252538; color: #e0e0e0;
        border: 1px solid #3a3a5a; border-radius: 8px;
        padding: 10px;
        font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;
    }
    QPushButton {
        background-color: #4a4a6a; color: white;
        border: none; padding: 10px 15px;
        border-radius: 6px; font-weight: 500;
    }
    QPushButton:hover  { background-color: #5a5a7a; }
    QPushButton:pressed { background-color: #3a3a5a; }
    QCheckBox { color: #e0e0e0; font-weight: 400; }
    QCheckBox::indicator {
        width: 18px; height: 18px;
        border: 2px solid #5a5a7a; border-radius: 4px;
        background-color: #252538;
    }
    QCheckBox::indicator:checked   { background-color: #6a6a9a; border: 2px solid #6a6a9a; }
    QCheckBox::indicator:unchecked { background-color: #252538; }
    QLabel  { color: #e0e0e0; font-weight: 500; }
    QFrame  { background-color: #252538; border-radius: 8px; border: 1px solid #3a3a5a; }
"""

LOG_SCROLLBAR_STYLE = """
    QTextEdit { background-color: #252538; color: #e0e0e0;
        border: 1px solid #3a3a5a; border-radius: 8px; padding: 10px;
        font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; }
    QTextEdit QScrollBar:vertical { background: #252538; width: 12px; margin: 0px; }
    QTextEdit QScrollBar::handle:vertical {
        background: #4a4a6a; border-radius: 6px; min-height: 20px; }
    QTextEdit QScrollBar::handle:vertical:hover { background: #5a5a7a; }
"""


# ---------------------------------------------------------------------------
# Stream redirector (stdout → log widget)
# ---------------------------------------------------------------------------

class StreamRedirector(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        self.text_written.emit(str(text))

    def flush(self):
        pass


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class ModernMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        # State
        self.cnc          = None
        self.robot_busy   = False
        self.in_alarm     = False   # True while GRBL is in alarm / recovering
        self.option1_enabled = False
        self.active_threads  = []

        # Styling helpers
        self.faint_style  = "color: #888888;"
        self.active_style = "color: rgb(0, 0, 0);"

        # GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.output(LED_PIN, GPIO.LOW)

        # Window
        self.setWindowTitle("MiniMax Controller")
        self.setGeometry(100, 100, 1400, 800)
        self.setStyleSheet(DARK_THEME)

        self._build_ui()

        # Serial + camera (after UI is built so logging works)
        self._initialize_serial_connection()
        self._redirect_stdout()

        self.log_text.append(
            "Application initialized. Toggle options and interact with controls.\n\n"
        )

        self.camera_thread = CameraWorker()
        self.camera_thread.frame_ready.connect(self._update_camera_view)
        self.camera_thread.start()

        # Auto-exposure refresh timer
        self.auto_update_timer = QTimer()
        self.auto_update_timer.timeout.connect(self._update_auto_values)
        self.auto_update_timer.start(200)

        # Apply initial exposure mode
        QTimer.singleShot(500, lambda: self._toggle_exposure_mode(0))

    # ======================================================================
    # UI construction
    # ======================================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        left  = QVBoxLayout()
        right = QVBoxLayout()
        main_layout.addLayout(left, 1)
        main_layout.addLayout(right, 5)

        self._build_camera_view(right)
        self._build_header(left)
        self._build_log_panel(left)
        self._build_action_buttons(left)
        self._build_controls_row(left)
        self._build_arrow_buttons(left)

        self._set_input_faint_defaults()

    def _build_camera_view(self, parent):
        self.camera_label = QLabel()
        self.camera_label.setMinimumSize(400, 300)
        self.camera_label.setStyleSheet("background-color: black;")
        self.camera_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        parent.addWidget(self.camera_label, 4)

    def _build_header(self, parent):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("MiniMax Controller")
        title.setStyleSheet("font-size: 20px; font-weight: 600; color: #6a6aff;")
        layout.addWidget(title)
        layout.addStretch()

        parent.addWidget(frame)

    def _build_log_panel(self, parent):
        """Log text area + exposure control side panel."""
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(250)
        self.log_text.setPlaceholderText("Output will appear here...")
        self.log_text.setStyleSheet(LOG_SCROLLBAR_STYLE)

        row = QHBoxLayout()
        row.addWidget(self.log_text, 4)
        row.addWidget(self._build_exposure_panel(), 1)

        parent.addLayout(row)

    def _build_exposure_panel(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)

        self.exposure_label = QLabel("Exposure")
        self.exposure_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.exposure_toggle = QCheckBox("Auto")
        self.exposure_toggle.setChecked(False)
        self.exposure_toggle.stateChanged.connect(self._toggle_exposure_mode)

        self.exposure_values    = [1 / (2 ** i) for i in range(1, 11)]
        self.exposure_us_values = [int(s * 1_000_000) for s in self.exposure_values]

        self.exposure_slider = QSlider(Qt.Orientation.Vertical)
        self.exposure_slider.setMinimum(0)
        self.exposure_slider.setMaximum(len(self.exposure_us_values) - 1)
        self.exposure_slider.setValue(4)
        self.exposure_slider.setEnabled(False)
        self.exposure_slider.valueChanged.connect(self._update_exposure)

        self.exposure_input = QLineEdit()
        self.exposure_input.setText("Enter exposure")
        self.exposure_input.setEnabled(False)
        self.exposure_input.returnPressed.connect(self._set_exposure_from_input)
        self.exposure_input.focusInEvent  = self._exposure_focus_in
        self.exposure_input.focusOutEvent = self._exposure_focus_out

        layout.addWidget(self.exposure_label)
        layout.addWidget(self.exposure_toggle)
        layout.addWidget(self.exposure_slider)
        layout.addWidget(self.exposure_input)

        return frame

    def _build_action_buttons(self, parent):
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.clear_button   = QPushButton("Clear Output")
        self.example_button = QPushButton("Run Example")
        self.input_button   = QPushButton("Get Input")
        self.center_button  = QPushButton("Go to Center")
        self.home_button    = QPushButton("Home CNC")
        self.picture_button = QPushButton("Take Pic")

        self.clear_button.clicked.connect(self._clear_output)
        self.example_button.clicked.connect(self._run_example)
        self.input_button.clicked.connect(self._get_user_input)
        self.center_button.clicked.connect(self._move_center)
        self.home_button.clicked.connect(self._safe_home)
        self.picture_button.clicked.connect(self._take_pic)

        for btn in (
            self.clear_button, self.example_button, self.input_button,
            self.center_button, self.home_button, self.picture_button,
        ):
            layout.addWidget(btn)
        layout.addStretch()

        parent.addWidget(frame)

    def _build_controls_row(self, parent):
        """LED toggle, step size, and gain slider."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(20)

        layout.addLayout(self._build_led_group(),  1)
        layout.addLayout(self._build_step_group(), 1)
        layout.addLayout(self._build_gain_group(), 4)

        parent.addWidget(frame)

    def _build_led_group(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        self.toggle_label1  = QLabel("LED")
        self.toggle_label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toggle_switch1 = QCheckBox()
        self.toggle_switch1.setChecked(False)
        self.toggle_switch1.stateChanged.connect(self._toggle_led)
        layout.addWidget(self.toggle_label1)
        layout.addWidget(self.toggle_switch1, alignment=Qt.AlignmentFlag.AlignCenter)
        return layout

    def _build_step_group(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        self.step_label = QLabel("Step Size")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step = QDoubleSpinBox()
        self.step.setRange(0.01, 100)
        self.step.setValue(1.0)
        layout.addWidget(self.step_label)
        layout.addWidget(self.step)
        return layout

    def _build_gain_group(self) -> QVBoxLayout:
        layout = QVBoxLayout()

        self.gain_label = QLabel("Gain: 0 dB")
        self.gain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row = QHBoxLayout()

        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setMinimum(0)
        self.gain_slider.setMaximum(51)
        self.gain_slider.setValue(0)
        self.gain_slider.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.gain_slider.valueChanged.connect(self._update_gain)

        self.gain_input = QLineEdit()
        self.gain_input.setText("Enter gain")
        self.gain_input.setFixedWidth(100)
        self.gain_input.setEnabled(False)
        self.gain_input.returnPressed.connect(self._set_gain_from_input)
        self.gain_input.focusInEvent  = self._gain_focus_in
        self.gain_input.focusOutEvent = self._gain_focus_out

        row.addWidget(self.gain_slider)
        row.addWidget(self.gain_input)

        layout.addWidget(self.gain_label)
        layout.addLayout(row)
        return layout

    def _build_arrow_buttons(self, parent):
        frame = QFrame()
        layout = QGridLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        btn_style = "font-size: 14px; padding: 10px;"

        self.up_button        = QPushButton("↑ Up")
        self.down_button      = QPushButton("↓ Down")
        self.left_button      = QPushButton("← Left")
        self.right_button     = QPushButton("→ Right")
        self.forward_button   = QPushButton("Forward")
        self.backwards_button = QPushButton("Backward")

        for btn in (self.up_button, self.down_button, self.left_button,
                    self.right_button, self.forward_button, self.backwards_button):
            btn.setStyleSheet(btn_style)

        self.up_button.clicked.connect(lambda: self._jog("Z",  1))
        self.down_button.clicked.connect(lambda: self._jog("Z", -1))
        self.left_button.clicked.connect(lambda: self._jog("X",  1))
        self.right_button.clicked.connect(lambda: self._jog("X", -1))
        self.forward_button.clicked.connect(lambda: self._jog("Y", -1))
        self.backwards_button.clicked.connect(lambda: self._jog("Y",  1))

        layout.addWidget(self.up_button,        0, 0)
        layout.addWidget(self.backwards_button, 0, 1)
        layout.addWidget(self.down_button,      0, 2)
        layout.addWidget(self.left_button,      1, 0)
        layout.addWidget(self.forward_button,   1, 1)
        layout.addWidget(self.right_button,     1, 2)

        parent.addWidget(frame)

    # ======================================================================
    # Initialisation helpers
    # ======================================================================

    def _initialize_serial_connection(self):
        try:
            self.print_with_timestamp("Connecting to GRBL...")
            self.cnc = CNCController(SERIAL_PORT, BAUD_RATE)
            self.print_with_timestamp("Serial connection established.")

            self.cnc.ser.write(b"\r\n\r\n")
            time.sleep(2)
            self.cnc.ser.flushInput()

            self.print_with_timestamp("GRBL ready.")
            self.print_with_timestamp("Unlocking GRBL...")
            self.cnc.send_command("$X\n")
            self.print_with_timestamp("Homing skipped (uncomment to enable).")

        except Exception as e:
            traceback.print_exc()
            self.print_with_timestamp(f"Failed to connect: {e}")
            self.cnc = None

    def _redirect_stdout(self):
        import sys
        self.stdout_redirector = StreamRedirector()
        self.stdout_redirector.text_written.connect(self._append_log)
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stdout_redirector

    # ======================================================================
    # Camera
    # ======================================================================

    def _update_camera_view(self, image: QImage):
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.camera_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_label.setPixmap(scaled)

    def _take_pic(self):
        try:
            raw_array = self.camera_thread.picam2.capture_array("raw")
            raw_data  = process_raw(raw_array, RGB=True, rgb_or_bgr=False)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base      = f"img_{timestamp}"

            cv2.imwrite(f"{base}.tiff", raw_data)

            raw_8bit = (raw_data / raw_data.max() * 255).astype(np.uint8)
            cv2.imwrite(f"{base}.jpg", raw_8bit)

            self.print_with_timestamp(f"Saved: {base}.tiff + {base}.jpg")

        except Exception as e:
            self.print_with_timestamp(f"Camera error: {e}")

    # ======================================================================
    # Exposure controls
    # ======================================================================

    def _set_input_faint_defaults(self):
        self.exposure_input.setText("Enter exposure")
        self.exposure_input.setStyleSheet(self.faint_style)
        self.gain_input.setText("Enter gain")
        self.gain_input.setStyleSheet(self.faint_style)

    @staticmethod
    def _format_exposure(exposure_us: int) -> str:
        if not exposure_us or exposure_us <= 0:
            return "?"
        seconds = exposure_us / 1_000_000
        if seconds >= 1:
            return str(int(seconds)) if seconds.is_integer() else f"{seconds:.1f}"
        return f"1/{round(1 / seconds)}"

    def _get_nearest_exposure_index(self, exposure_us: int) -> int:
        return min(
            range(len(self.exposure_us_values)),
            key=lambda i: abs(self.exposure_us_values[i] - exposure_us),
        )

    def _toggle_exposure_mode(self, state):
        auto = self.exposure_toggle.isChecked()
        try:
            if auto:
                self.camera_thread.picam2.set_controls({"AeEnable": True})
                self.exposure_slider.setEnabled(False)
                self.gain_slider.setEnabled(False)
                self.exposure_input.setEnabled(False)
                self.gain_input.setEnabled(False)
                self.exposure_label.setText("Exposure\nAuto")
                self.gain_label.setText("Analog Gain (Auto)")
                self.print_with_timestamp("Auto Exposure + Gain Enabled")
            else:
                self.exposure_input.setEnabled(True)
                self.gain_input.setEnabled(True)
                self._set_input_faint_defaults()

                metadata = self.camera_thread.picam2.capture_metadata()
                exposure = metadata.get("ExposureTime")
                gain     = metadata.get("AnalogueGain")

                self.camera_thread.picam2.set_controls({"AeEnable": False})

                if exposure is not None:
                    idx = self._get_nearest_exposure_index(exposure)
                    self.exposure_slider.blockSignals(True)
                    self.exposure_slider.setValue(idx)
                    self.exposure_slider.blockSignals(False)
                    self.exposure_label.setText(
                        f"Exposure\n{self._format_exposure(self.exposure_us_values[idx])}"
                    )

                if gain is not None:
                    db_val = self._gain_to_db(gain)
                    self.gain_slider.blockSignals(True)
                    self.gain_slider.setValue(db_val)
                    self.gain_slider.blockSignals(False)
                    self.gain_label.setText(f"Gain: {db_val} dB")

                self.exposure_slider.setEnabled(True)
                self.gain_slider.setEnabled(True)
                self.print_with_timestamp("Manual Exposure + Gain Enabled")

        except Exception as e:
            self.print_with_timestamp(f"Exposure toggle error: {e}")

    def _update_exposure(self, index: int):
        if self.exposure_toggle.isChecked():
            return
        try:
            exposure_us = self.exposure_us_values[index]
            self.exposure_slider.blockSignals(True)
            self.exposure_input.blockSignals(True)
            self.exposure_input.setText(self._format_exposure(exposure_us))
            self.camera_thread.picam2.set_controls({"ExposureTime": exposure_us})
            self.exposure_label.setText(f"Exposure\n{self._format_exposure(exposure_us)}")
        except Exception as e:
            self.print_with_timestamp(f"Exposure error: {e}")
        finally:
            self.exposure_slider.blockSignals(False)
            self.exposure_input.blockSignals(False)

    def _set_exposure_from_input(self):
        if self.exposure_toggle.isChecked():
            return
        text = self.exposure_input.text().strip()
        try:
            if "/" in text:
                num, denom = text.split("/")
                seconds = float(num) / float(denom)
            else:
                seconds = float(text)

            exposure_us = int(seconds * 1_000_000)
            if exposure_us <= 0:
                raise ValueError("Exposure must be positive")

            self.camera_thread.picam2.set_controls({"ExposureTime": exposure_us})
            self.exposure_label.setText(
                f"Exposure\n{self._format_exposure(exposure_us)}"
            )

            idx = self._get_nearest_exposure_index(exposure_us)
            self.exposure_slider.blockSignals(True)
            self.exposure_slider.setValue(idx)
            self.exposure_slider.blockSignals(False)

            self.exposure_input.setText("Enter exposure")
            self.exposure_input.setStyleSheet(self.faint_style)

        except Exception:
            self.print_with_timestamp(f"Invalid exposure input: {text}")

    def _exposure_focus_in(self, event):
        if self.exposure_input.text() == "Enter exposure":
            self.exposure_input.clear()
        self.exposure_input.setStyleSheet(self.active_style)
        QLineEdit.focusInEvent(self.exposure_input, event)

    def _exposure_focus_out(self, event):
        if not self.exposure_input.text().strip():
            self.exposure_input.setText("Enter exposure")
            self.exposure_input.setStyleSheet(self.faint_style)
        QLineEdit.focusOutEvent(self.exposure_input, event)

    # ======================================================================
    # Gain controls
    # ======================================================================

    @staticmethod
    def _gain_to_db(gain: float) -> int:
        return int(round(20 * math.log10(gain)))

    def _update_gain(self, db_value: int):
        if self.exposure_toggle.isChecked():
            return
        try:
            self.gain_slider.blockSignals(True)
            self.gain_input.blockSignals(True)
            self.gain_input.setText(str(db_value))
            self.camera_thread.picam2.set_controls({"AnalogueGain": db_value})
            self.gain_label.setText(f"Gain: {db_value} dB")
        except Exception as e:
            self.print_with_timestamp(f"Gain error: {e}")
        finally:
            self.gain_slider.blockSignals(False)
            self.gain_input.blockSignals(False)

    def _set_gain_from_input(self):
        if self.exposure_toggle.isChecked():
            return
        text = self.gain_input.text().strip()
        try:
            db_value = float(text)
            self.camera_thread.picam2.set_controls({"AnalogueGain": db_value})
            self.gain_label.setText(f"Gain: {db_value} dB")
            self.gain_slider.blockSignals(True)
            self.gain_slider.setValue(int(db_value))
            self.gain_slider.blockSignals(False)
            self.gain_input.setText("Enter gain")
            self.gain_input.setStyleSheet(self.faint_style)
        except Exception:
            self.print_with_timestamp(f"Invalid gain input: {text}")

    def _gain_focus_in(self, event):
        if self.gain_input.text() == "Enter gain":
            self.gain_input.clear()
        self.gain_input.setStyleSheet(self.active_style)
        QLineEdit.focusInEvent(self.gain_input, event)

    def _gain_focus_out(self, event):
        if not self.gain_input.text().strip():
            self.gain_input.setText("Enter gain")
            self.gain_input.setStyleSheet(self.faint_style)
        QLineEdit.focusOutEvent(self.gain_input, event)

    def _update_auto_values(self):
        """Refresh exposure/gain labels while auto mode is active."""
        if not self.exposure_toggle.isChecked():
            return
        try:
            metadata = self.camera_thread.picam2.capture_metadata()
            exposure = metadata.get("ExposureTime")
            gain     = metadata.get("AnalogueGain")

            if exposure is not None:
                idx = self._get_nearest_exposure_index(exposure)
                self.exposure_slider.blockSignals(True)
                self.exposure_slider.setValue(idx)
                self.exposure_slider.blockSignals(False)
                self.exposure_label.setText(
                    f"Exposure\n{self._format_exposure(self.exposure_us_values[idx])}"
                )

            if gain is not None:
                db_val = self._gain_to_db(gain)
                self.gain_slider.blockSignals(True)
                self.gain_slider.setValue(db_val)
                self.gain_slider.blockSignals(False)
                self.gain_label.setText(f"Gain: {db_val} dB")

        except Exception as e:
            self.print_with_timestamp(f"Auto update error: {e}")

    # ======================================================================
    # CNC motion
    # ======================================================================

    def _jog(self, axis: str, direction: int):
        dlog(f" _jog called — robot_busy={self.robot_busy} in_alarm={self.in_alarm}")
        if self.robot_busy or self.in_alarm:
            dlog(" _jog blocked — returning early")
            return

        self.robot_busy = True
        self._set_motion_buttons_enabled(False)

        step = self.step.value() * direction
        pos  = self.cnc.get_current_position()

        if pos is None:
            dlog(" _jog: get_current_position returned None — aborting, triggering alarm")
            self.robot_busy = False
            self._on_alarm()
            return

        dlog(f" _jog: moving axis={axis} step={step} pos={pos}")
        pos[{"X": "x_pos", "Y": "y_pos", "Z": "z_pos"}[axis]] += step

        self._start_cnc_thread("jog", pos)

    def _safe_home(self):
        if self.robot_busy or self.in_alarm:
            return
        self.robot_busy = True
        self._set_motion_buttons_enabled(False)
        self.print_with_timestamp("Starting homing cycle...")
        self._start_cnc_thread("home")

    def _move_center(self):
        if self.robot_busy or self.in_alarm:
            return
        self.robot_busy = True
        self._set_motion_buttons_enabled(False)
        self.print_with_timestamp("Moving to Center")
        self._start_cnc_thread("jog", CENTER_POS.copy())

    def _start_cnc_thread(self, command_type: str, data=None):
        thread = CNCWorker(self.cnc, command_type, data)
        self.active_threads.append(thread)
        # QueuedConnection: signal is always delivered on the main thread,
        # so _on_alarm can safely touch the UI and start a new QThread.
        thread.alarm_triggered.connect(
            self._on_alarm, Qt.ConnectionType.QueuedConnection
        )
        thread.finished.connect(self._motion_finished)
        thread.finished.connect(lambda: self.active_threads.remove(thread))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _motion_finished(self):
        dlog(f" _motion_finished — in_alarm={self.in_alarm} robot_busy={self.robot_busy}")
        if self.in_alarm:
            dlog(" _motion_finished: in_alarm is True, skipping re-enable")
            return
        self.robot_busy = False
        self._set_motion_buttons_enabled(True)

    def _set_motion_buttons_enabled(self, enabled: bool):
        for btn in (
            self.up_button, self.down_button, self.left_button,
            self.right_button, self.forward_button, self.backwards_button,
            self.center_button, self.home_button,
        ):
            btn.setEnabled(enabled)

    def _on_alarm(self):
        """Runs on the main thread (QueuedConnection).

        Guards against double-firing: if recovery is already running, ignore.
        """
        if self.in_alarm:
            dlog("_on_alarm: already in alarm — ignoring duplicate signal")
            return

        dlog(f"_on_alarm fired — setting in_alarm=True")
        self.in_alarm   = True
        self.robot_busy = True
        self._start_recovery()

    def _start_recovery(self):
        """Lock buttons and start the reset → unlock → home recovery thread."""
        dlog(f"_start_recovery — in_alarm={self.in_alarm} robot_busy={self.robot_busy}")
        self._set_motion_buttons_enabled(False)
        self.print_with_timestamp("⚠️ ALARM — limit switch hit. Resetting and re-homing...")

        thread = CNCWorker(self.cnc, "recover")
        self.active_threads.append(thread)

        thread.alarm_triggered.connect(self._on_recovery_failed)
        thread.finished.connect(self._on_recovery_finished)
        thread.finished.connect(lambda: self.active_threads.remove(thread))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_recovery_finished(self):
        dlog(" _on_recovery_finished — clearing in_alarm, re-enabling buttons")
        self.in_alarm   = False
        self.robot_busy = False
        self._set_motion_buttons_enabled(True)
        self.print_with_timestamp("Recovery complete. Motion re-enabled.")

    def _on_recovery_failed(self):
        # Leave in_alarm = True and buttons disabled
        self.print_with_timestamp(
            "⚠️ Recovery failed. Check the machine manually before moving."
        )

    # ======================================================================
    # GPIO / LED
    # ======================================================================

    def _toggle_led(self, state):
        on = self.toggle_switch1.checkState().value != 0
        self.option1_enabled = on
        if on:
            GPIO.output(LED_PIN, GPIO.HIGH)
            self.print_with_timestamp("LED turned on")
        else:
            GPIO.output(LED_PIN, GPIO.LOW)
            self.print_with_timestamp("LED turned off")

    # ======================================================================
    # Log / output helpers
    # ======================================================================

    def print_with_timestamp(self, message: str):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        print(f"{timestamp} - {message}")

    def _append_log(self, text: str):
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def _clear_output(self):
        self.log_text.clear()
        self.print_with_timestamp("Output cleared")

    # ======================================================================
    # Button actions
    # ======================================================================

    def _get_user_input(self):
        text, ok = QInputDialog.getText(self, "Send Command to GRBL", "Enter GRBL command:")
        if not (ok and text):
            self.print_with_timestamp("No command entered")
            return

        command = text.strip()
        if not command.endswith("\n"):
            command += "\n"

        self.print_with_timestamp(f"> {command.strip()}")
        try:
            _, out = self.cnc.send_command(command)
            for line in out:
                if line:
                    self.print_with_timestamp(line)
        except Exception as e:
            self.print_with_timestamp(f"Error: {e}")

    def _run_example(self):
        self.print_with_timestamp("Starting example with delay...")
        self._delay_counter = 0
        self._delay_sequence()

    def _delay_sequence(self):
        if self._delay_counter < 5:
            self.print_with_timestamp(f"Processing step {self._delay_counter + 1}...")
            self._delay_counter += 1
            QTimer.singleShot(1000, self._delay_sequence)
        else:
            self.print_with_timestamp("Example completed!")

    # ======================================================================
    # Window close
    # ======================================================================

    def closeEvent(self, event):
        print("Closing application...")

        try:
            GPIO.output(LED_PIN, GPIO.LOW)
            GPIO.cleanup()
            print("GPIO cleaned up")
        except Exception as e:
            print(f"GPIO cleanup error: {e}")

        try:
            if hasattr(self, "camera_thread"):
                self.camera_thread.stop()
                print("Camera stopped")
        except Exception as e:
            print(f"Camera cleanup error: {e}")

        try:
            if self.cnc is not None:
                self.cnc.close_connection()
                print("CNC disconnected")
        except Exception as e:
            print(f"CNC cleanup error: {e}")

        event.accept()