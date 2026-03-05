import sys, time, json, re
from queue import Queue, Empty
from focus import run_autofocus_at_current_position

import numpy as np
import cv2
import serial

from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot, QEvent
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTextEdit, QDoubleSpinBox, QGroupBox, QCheckBox, QLineEdit
)

from picamera2 import Picamera2
import libcamera

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except Exception:
    HAS_GPIO = False


# ----------------------------
# Helpers
# ----------------------------
def sort_dict(d):
    d_keys = list(d.keys())
    d_keys.sort()
    return {i: d[i] for i in d_keys}

def process_raw(input_array, RGB=True, rgb_or_bgr=False, mono=False,
                R=False, G=False, G1=False, G2=False, B=False, RGB2=False):
    if 'uint16' not in str(input_array.dtype):
        input_array = input_array.view(np.uint16)
        if mono:
            return input_array

    if R or G or B or G1 or G2 or RGB2:
        RGB = False

    if RGB:
        blue_pixels  = input_array[0::2, 0::2]
        red_pixels   = input_array[1::2, 1::2]
        green1_pixels = input_array[0::2, 1::2]
        green2_pixels = input_array[1::2, 0::2]

        avg_green = ((green1_pixels & green2_pixels) + (green1_pixels ^ green2_pixels) / 2).astype(np.uint16)

        if rgb_or_bgr:
            out = np.asarray([red_pixels, avg_green, blue_pixels]).transpose(1, 2, 0)
        else:
            out = np.asarray([blue_pixels, avg_green, red_pixels]).transpose(1, 2, 0)

    if R:
        out = input_array[1::2, 1::2]
    if G:
        green1_pixels = input_array[0::2, 1::2]
        green2_pixels = input_array[1::2, 0::2]
        out = ((green1_pixels & green2_pixels) + (green1_pixels ^ green2_pixels) / 2).astype(np.uint16)
    if G1:
        out = input_array[0::2, 1::2]
    if G2:
        out = input_array[1::2, 0::2]
    if B:
        out = input_array[0::2, 0::2]
    if RGB2:
        blue_pixels  = input_array[0::2, 0::2]
        red_pixels   = input_array[1::2, 1::2]
        green1_pixels = input_array[0::2, 1::2]
        green2_pixels = input_array[1::2, 0::2]
        a = np.concatenate((red_pixels, green1_pixels), axis=0)
        b = np.concatenate((green2_pixels, blue_pixels), axis=0)
        out = np.concatenate((a, b), axis=1)

    return out

def draw_crosshair(img_bgr, color=(0, 255, 0), line_len=60):
    h, w = img_bgr.shape[:2]
    cx, cy = w // 2, h // 2
    cv2.line(img_bgr, (cx - line_len, cy), (cx + line_len, cy), color, 1)
    cv2.line(img_bgr, (cx, cy - line_len), (cx, cy + line_len), color, 1)
    return img_bgr

_GRBL_MPOS_RE = re.compile(r"MPos:([-\d.]+),([-\d.]+),([-\d.]+)")

def parse_mpos(line: str):
    m = _GRBL_MPOS_RE.search(line)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3))

# ----------------------------
# CNC Worker Thread
# ----------------------------
class CNCWorker(QThread):
    alarm_detected = Signal()
    log = Signal(str)
    position = Signal(str)
    busy_changed = Signal(bool)
    connected = Signal(bool)

    def enqueue_bytes(self, payload: bytes):
        self._q.put(payload)

    def __init__(self, port: str, baud: int):
        super().__init__()
        self.port = port
        self.baud = baud
        self._q = Queue()
        self._running = True
        self._ser = None
        self._busy = False

    def set_busy(self, v: bool):
        if self._busy != v:
            self._busy = v
            self.busy_changed.emit(v)

    def enqueue(self, cmd: str):
        self._q.put(cmd)

    def stop(self):
        self._running = False
        self._q.put(None)

    def _readline_nonempty(self, timeout_s=2.0):
        start = time.time()
        while time.time() - start < timeout_s:
            try:
                line = self._ser.readline().decode(errors="ignore").strip()
            except Exception:
                line = ""
            if line:
                return line
        return ""

    def run(self):
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
            time.sleep(2)
            self.log.emit(f"Connected to CNC on {self.port} @ {self.baud}")
            self.connected.emit(True)
            self._ser.write(b"G91\n")  # relative mode
        except Exception as e:
            self.log.emit(f"FAILED to open serial: {e}")
            self.connected.emit(False)
            return

        while self._running:
            try:
                item = self._q.get(timeout=0.1)
            except Empty:
                continue

            if item is None:
                break

            try:
                self.set_busy(True)

                # --- REAL-TIME BYTES (Ctrl-X reset etc.) ---
                if isinstance(item, (bytes, bytearray)):
                    try:
                        self._ser.write(item)
                        self._ser.flush()
                        self.log.emit(f"> [bytes] {item!r}")
                        time.sleep(0.15)
                        # After Ctrl-X GRBL often prints its startup line
                        for _ in range(10):
                            line = self._readline_nonempty(timeout_s=0.25)
                            if line:
                                self.log.emit(line)
                    except Exception as e:
                        self.log.emit(f"Byte write error: {e}")
                    finally:
                        self.set_busy(False)
                    continue

                cmd = str(item).strip()
                if not cmd:
                    self.set_busy(False)
                    continue

                # Status query: realtime, no newline
                if cmd == "?":
                    self._ser.write(b"?")
                    self._ser.flush()
                    self.log.emit("> ?")
                    time.sleep(0.05)

                    for _ in range(25):
                        line = self._readline_nonempty(timeout_s=0.4)
                        if not line:
                            continue
                        self.log.emit(line)
                        if "MPos:" in line:
                            self.position.emit(line)
                            break

                    self.set_busy(False)
                    continue

                # Normal commands: send with newline
                self._ser.reset_input_buffer()
                self._ser.write((cmd + "\n").encode())
                self._ser.flush()
                self.log.emit(f"> {cmd}")

                # Wait for ok/error/alarm
                for _ in range(250):
                    line = self._readline_nonempty(timeout_s=0.4)
                    if not line:
                        continue
                    self.log.emit(line)
                    low = line.lower()
                    if "alarm" in low:
                        self.log.emit("MACHINE ENTERED ALARM STATE")
                        self.alarm_detected.emit()   # NEW SIGNAL
                        break
                    if low == "ok" or "error" in low:
                        break
            except Exception as e:
                self.log.emit(f"Serial error: {e}")
            finally:
                self.set_busy(False)

        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass
        self.log.emit("CNC thread stopped.")
        self.connected.emit(False)

# ----------------------------
# Autofocus Worker Thread
# ----------------------------
class AutofocusWorker(QThread):
    log = Signal(str)
    finished = Signal(bool, float)  # (ok, best_z)

    def __init__(self, port: str, baud: int, starting_location: dict, cam):
        super().__init__()
        self.port = port
        self.baud = baud
        self.starting_location = starting_location
        self.cam = cam

    def run(self):
        ser = None
        best_z = float("nan")
        try:
            self.log.emit("Autofocus: opening serial...")
            ser = serial.Serial(self.port, self.baud, timeout=0.2)
            time.sleep(2)

            def _write_and_wait_ok(ser, cmd: str, timeout=2.0):
                ser.write((cmd + "\n").encode())
                ser.flush()
                t0 = time.time()
                while time.time() - t0 < timeout:
                    line = ser.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    low = line.lower()
                    if low == "ok" or "error" in low or "alarm" in low:
                        return line
                return ""
            # After opening serial
            ser.write(b"\r\n\r\n")
            ser.flush()
            time.sleep(0.2)
            ser.reset_input_buffer()

            # Unlock
            resp = _write_and_wait_ok(ser, "$X", timeout=3.0)
            self.log.emit(f"Autofocus: $X -> {resp}")

            # Set mode you expect (pick ONE that matches your move_to)
            resp = _write_and_wait_ok(ser, "G90", timeout=2.0)  # absolute mode
            self.log.emit(f"Autofocus: G90 -> {resp}")

            self.log.emit(f"Autofocus: starting at {self.starting_location}")
            best_z, *_ = run_autofocus_at_current_position(
                ser=ser,
                starting_location=self.starting_location,
                cam=self.cam,
                verbose=True
            )
            self.log.emit(f"Autofocus: done. Best Z = {best_z}")
            self.finished.emit(True, float(best_z))
        except Exception as e:
            self.log.emit(f"Autofocus error: {e}")
            self.finished.emit(False, best_z)
        finally:
            try:
                if ser:
                    ser.close()
            except Exception:
                pass

# ----------------------------
# Main GUI
# ----------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.alarm_state = False
        self.setWindowTitle("CNC + Camera GUI")

        # ---- Settings ----
        self.SERIAL_PORT = "/dev/ttyUSB0"
        self.BAUD_RATE = 115200
        self.settings_path = "/home/r/rpi_camera_tests/camera_settings.txt"

        # ---- State ----
        self.default_image_settings = {}
        self.busy = False

        # ---- UI ----
        self.preview = QLabel("Preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(640, 480)

        self.logbox = QTextEdit()
        self.logbox.setReadOnly(True)

        self.step = QDoubleSpinBox()
        self.step.setRange(0.01, 100.0)
        self.step.setSingleStep(0.1)
        self.step.setValue(1.0)

        self.gpio_checkbox = QCheckBox("GPIO26 ON")
        self.gpio_checkbox.setChecked(False)
        self.gpio_checkbox.setEnabled(HAS_GPIO)

        # --- autofocus ---
        self.autofocus_running = False
        self.current_pos = {"x_pos": 0.0, "y_pos": 0.0, "z_pos": 0.0}

        # --- GRBL command entry ---
        self.cmd_entry = QLineEdit()
        self.cmd_entry.setPlaceholderText("Type GRBL/G-code (e.g., $$, $G, G0 X10, ?)")

        btn_send_cmd = QPushButton("Send")
        btn_send_cmd.clicked.connect(self.send_custom_command)
        self.cmd_entry.returnPressed.connect(self.send_custom_command)

        # Movement buttons
        btn_up = QPushButton("Y+")
        btn_down = QPushButton("Y-")
        btn_left = QPushButton("X+")
        btn_right = QPushButton("X-")
        btn_zup = QPushButton("Z+")
        btn_zdown = QPushButton("Z-")

        btn_home = QPushButton("Home ($H)")
        btn_unlock = QPushButton("Unlock ($X)")
        btn_pos = QPushButton("Get Pos (?)")
        btn_soft_reset = QPushButton("Soft Reset")
        btn_soft_reset.clicked.connect(self.soft_reset)
        btn_autofocus = QPushButton("Autofocus")


        # Wire actions
        btn_up.clicked.connect(lambda: self.move("Y", +1))
        btn_down.clicked.connect(lambda: self.move("Y", -1))
        btn_left.clicked.connect(lambda: self.move("X", +1))
        btn_right.clicked.connect(lambda: self.move("X", -1))
        btn_zup.clicked.connect(lambda: self.move("Z", +1))
        btn_zdown.clicked.connect(lambda: self.move("Z", -1))

        btn_home.clicked.connect(lambda: self.send("$H"))
        btn_unlock.clicked.connect(lambda: self.send("$X"))
        btn_pos.clicked.connect(lambda: self.send("?"))
        btn_autofocus.clicked.connect(self.start_autofocus)

        self.gpio_checkbox.stateChanged.connect(self.on_gpio_toggle)

        # Layout
        move_group = QGroupBox("Jog Controls")
        g = QGridLayout()
        g.addWidget(btn_zup,   0, 0, 1, 2)
        g.addWidget(btn_up,    1, 0, 1, 2)
        g.addWidget(btn_left,  2, 0)
        g.addWidget(btn_right, 2, 1)
        g.addWidget(btn_down,  3, 0, 1, 2)
        g.addWidget(btn_zdown, 4, 0, 1, 2)
        move_group.setLayout(g)

        top_controls = QHBoxLayout()
        top_controls.addWidget(QLabel("Step:"))
        top_controls.addWidget(self.step)
        top_controls.addStretch(1)
        top_controls.addWidget(btn_unlock)
        top_controls.addWidget(btn_home)
        top_controls.addWidget(btn_pos)
        top_controls.addWidget(self.gpio_checkbox)
        top_controls.addWidget(btn_soft_reset)
        top_controls.addWidget(btn_autofocus)

        cmd_row = QHBoxLayout()
        cmd_row.addWidget(QLabel("GRBL Command:"))
        cmd_row.addWidget(self.cmd_entry, 1)
        cmd_row.addWidget(btn_send_cmd)

        left = QVBoxLayout()
        left.addWidget(self.preview)
        left.addLayout(top_controls)
        left.addLayout(cmd_row)

        right = QVBoxLayout()
        right.addWidget(move_group)
        right.addWidget(QLabel("Log"))
        right.addWidget(self.logbox)

        main = QHBoxLayout()
        main.addLayout(left, 2)
        main.addLayout(right, 1)
        self.setLayout(main)

        self._controls_to_disable = [
            btn_autofocus,
            btn_unlock, btn_home, btn_pos, btn_soft_reset,
            btn_up, btn_down, btn_left, btn_right, btn_zup, btn_zdown,
            btn_send_cmd,
            self.cmd_entry,
            self.step,
            self.gpio_checkbox,
        ]

        # --- Keyboard jog controls ---
        self.enable_key_jog = True

        # Make sure the window can receive key events
        self.setFocusPolicy(Qt.StrongFocus)

        # Catch key presses even when a child widget has focus
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        # Optional: avoid arrow keys changing spinbox value instead of jogging
        self.step.setKeyboardTracking(False)

        # ---- CNC worker ----
        self.cnc = CNCWorker(self.SERIAL_PORT, self.BAUD_RATE)
        self.cnc.log.connect(self.append_log)
        self.cnc.busy_changed.connect(self.on_busy_changed)
        self.cnc.position.connect(self.on_position_line)
        self.cnc.connected.connect(self.on_cnc_connected)
        self.cnc.start()
        self.cnc.alarm_detected.connect(self.on_alarm)

        # ---- Camera ----
        self.picam2 = Picamera2()
        self.configure_camera()
        self.picam2.start()

        # Preview timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_preview)
        self.timer.start(33)

        if HAS_GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(26, GPIO.OUT)
            self.on_gpio_toggle(
                Qt.CheckState.Checked.value if self.gpio_checkbox.isChecked()
                else Qt.CheckState.Unchecked.value
            )
    def on_alarm(self):
        self.alarm_state = True
        self.append_log("Machine locked due to ALARM.")

    def start_autofocus(self):
        if self.autofocus_running:
            return

        self.autofocus_running = True
        self.enable_key_jog = False
        self.set_controls_enabled(False)

        # Stop preview captures so autofocus owns the camera
        try:
            self.timer.stop()
        except Exception:
            pass

        # Stop CNC worker so it releases the serial port
        try:
            self.append_log("Stopping CNC thread for autofocus...")
            self.cnc.stop()
            self.cnc.wait(2000)
        except Exception as e:
            self.append_log(f"Warning: CNC thread stop issue: {e}")

        # Refresh position once
        self.send("?")
        QApplication.processEvents()
        time.sleep(0.1)

        # Use the best known position as the starting location
        starting_location = dict(self.current_pos)

        self.append_log("Starting autofocus (CNC + camera locked)...")
        self.af_worker = AutofocusWorker(self.SERIAL_PORT, self.BAUD_RATE, starting_location, self.picam2)
        self.af_worker.log.connect(self.append_log)
        self.af_worker.finished.connect(self.on_autofocus_finished)
        self.af_worker.start()


    @Slot(bool, float)
    def on_autofocus_finished(self, ok: bool, best_z: float):
        self.append_log(f"Autofocus finished: {'OK' if ok else 'FAILED'}")

        # Update our estimated z position if autofocus succeeded
        if ok and best_z == best_z:  # not NaN
            self.current_pos["z_pos"] = float(best_z)

        # Restart CNC worker
        try:
            self.append_log("Restarting CNC thread...")
            self.cnc = CNCWorker(self.SERIAL_PORT, self.BAUD_RATE)
            self.cnc.log.connect(self.append_log)
            self.cnc.busy_changed.connect(self.on_busy_changed)
            self.cnc.position.connect(self.on_position_line)
            self.cnc.connected.connect(self.on_cnc_connected)
            self.cnc.start()
        except Exception as e:
            self.append_log(f"Failed to restart CNC: {e}")

        # Resume preview timer
        try:
            self.timer.start(33)
        except Exception:
            pass

        self.autofocus_running = False
        self.enable_key_jog = True
        self.set_controls_enabled(True)

    def set_controls_enabled(self, enabled: bool):
        for w in getattr(self, "_controls_to_disable", []):
            w.setEnabled(enabled)

    def eventFilter(self, obj, event):
        if not self.enable_key_jog:
            return super().eventFilter(obj, event)
        
        if self.autofocus_running:
            return super().eventFilter(obj, event)

        if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
            key = event.key()

            # Don't jog while typing a command
            if self.cmd_entry.hasFocus():
                return super().eventFilter(obj, event)

            if key == Qt.Key_Up:
                self.move("Y", +1)
                return True
            if key == Qt.Key_Down:
                self.move("Y", -1)
                return True
            if key == Qt.Key_Left:
                self.move("X", +1)
                return True
            if key == Qt.Key_Right:
                self.move("X", -1)
                return True

            # + / - for Z (support main keyboard and numpad)
            if key in (Qt.Key_Plus, Qt.Key_Equal):   # '=' is often '+' with shift
                self.move("Z", +1)
                return True
            if key in (Qt.Key_Minus, Qt.Key_Underscore):
                self.move("Z", -1)
                return True

        return super().eventFilter(obj, event)

    def configure_camera(self):
        cam_config = self.picam2.create_preview_configuration(
            main={"format": "BGR888", "size": (640, 480)},
            raw={"format": "SRGGB12", "size": (2028, 1520)},
            display="main",
            queue=False,
            buffer_count=4
        )
        cam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
        self.picam2.configure(cam_config)

        try:
            with open(self.settings_path, "r") as f:
                self.default_image_settings = sort_dict(json.loads(f.read()))
            for k, v in self.default_image_settings.items():
                try:
                    self.picam2.set_controls({k: v})
                except Exception:
                    self.append_log(f"Camera setting failed: {k} = {v}")
        except Exception as e:
            self.append_log(f"Could not load camera settings: {e}")

        exp_time = 1/60
        exp_us = int(round(exp_time * 1_000_000))
        try:
            self.picam2.set_controls({"ExposureTime": exp_us})
        except Exception:
            pass

    def soft_reset(self):
        self.append_log("Sending soft reset (Ctrl-X)...")
        self.cnc.enqueue_bytes(b"\x18")
        self.alarm_state = False

    @Slot()
    def update_preview(self):
        try:
            frame = self.picam2.capture_array("main")
            frame = draw_crosshair(frame)
            h, w = frame.shape[:2]
            qimg = QImage(frame.data, w, h, 3*w, QImage.Format_BGR888)
            self.preview.setPixmap(QPixmap.fromImage(qimg).scaled(
                self.preview.width(), self.preview.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        except Exception as e:
            self.append_log(f"Preview error: {e}")

    def move(self, axis: str, direction: int):
        step = float(self.step.value()) * direction
        if axis == "X":
            self.current_pos["x_pos"] += step
            self.send(f"G91 G0 X{step}")
        elif axis == "Y":
            self.current_pos["y_pos"] += step
            self.send(f"G91 G0 Y{step}")
        elif axis == "Z":
            self.current_pos["z_pos"] += step
            self.send(f"G91 G0 Z{step}")

    def send(self, cmd: str):
        cmd = cmd.strip()

        if self.alarm_state:
            allowed = {"\x18", "$X"}  # soft reset + unlock
            if cmd not in allowed:
                self.append_log("Machine in ALARM. Reset required.")
                return

        if self.autofocus_running:
            self.append_log("Autofocus running; command ignored.")
            return

        always_allow = {"?", "$X", "$H"}
        if self.busy and cmd not in always_allow:
            self.append_log("Machine busy; command ignored.")
            return
        self.cnc.enqueue(cmd)

    def send_custom_command(self):
        cmd = self.cmd_entry.text().strip()
        if not cmd:
            return
        self.send(cmd)
        self.cmd_entry.clear()

    @Slot(bool)
    def on_busy_changed(self, v: bool):
        self.busy = v

    @Slot(bool)
    def on_cnc_connected(self, ok: bool):
        if not ok:
            self.append_log("CNC not connected (or disconnected).")

    @Slot(str)
    def on_position_line(self, line: str):
        self.append_log(f"[POS] {line}")

        mpos = parse_mpos(line)
        if mpos:
            x, y, z = mpos
            self.current_pos["x_pos"] = x
            self.current_pos["y_pos"] = y
            self.current_pos["z_pos"] = z

    @Slot(str)
    def append_log(self, msg: str):
        self.logbox.append(msg)

    @Slot(int)
    def on_gpio_toggle(self, state: int):
        if not HAS_GPIO:
            return
        try:
            is_checked = (state == Qt.CheckState.Checked.value)
            GPIO.output(26, GPIO.HIGH if is_checked else GPIO.LOW)
            self.append_log(f"GPIO26 -> {'HIGH' if is_checked else 'LOW'}")
        except Exception as e:
            self.append_log(f"GPIO error: {e}")

    def closeEvent(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass

        try:
            self.cnc.stop()
            self.cnc.wait(1500)
        except Exception:
            pass

        try:
            self.picam2.stop()
        except Exception:
            pass

        if HAS_GPIO:
            try:
                GPIO.cleanup()
            except Exception:
                pass

        event.accept()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()






