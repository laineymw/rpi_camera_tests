# =========================
# IMPORTS
# =========================
import sys
import time
import datetime
import traceback
import math
import atexit

import serial
import RPi.GPIO as GPIO
import cv2
import numpy as np

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QTextCursor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QPushButton, QLabel, QFrame,
    QInputDialog, QCheckBox,
    QSlider, QSpinBox, QDoubleSpinBox,
    QSizePolicy
)


# =========================
# IMAGE PROCESSING
# =========================
def process_raw(input_array, R=False, G=False, G1=False, G2=False,
                B=False, RGB=True, RGB2=False, rgb_or_bgr=True, mono=False):

    if 'uint16' not in str(input_array.dtype):
        input_array = input_array.view(np.uint16)
        if mono:
            return input_array

    if R or G or B or G1 or G2 or RGB2:
        RGB = False

    if RGB:
        blue_pixels = input_array[0::2, 0::2]
        red_pixels = input_array[1::2, 1::2]
        green1_pixels = input_array[0::2, 1::2]
        green2_pixels = input_array[1::2, 0::2]

        avg_green = ((green1_pixels & green2_pixels) +
                     (green1_pixels ^ green2_pixels) / 2).astype(np.uint16)

        if rgb_or_bgr:
            out = np.asarray([red_pixels, avg_green, blue_pixels]).transpose(1, 2, 0)
        else:
            out = np.asarray([blue_pixels, avg_green, red_pixels]).transpose(1, 2, 0)

    if R:
        out = input_array[1::2, 1::2]

    if G:
        green1_pixels = input_array[0::2, 1::2]
        green2_pixels = input_array[1::2, 0::2]
        out = ((green1_pixels & green2_pixels) +
               (green1_pixels ^ green2_pixels) / 2).astype(np.uint16)

    if G1:
        out = input_array[0::2, 1::2]

    if G2:
        out = input_array[1::2, 0::2]

    if B:
        out = input_array[0::2, 0::2]

    if RGB2:
        blue_pixels = input_array[0::2, 0::2]
        red_pixels = input_array[1::2, 1::2]
        green1_pixels = input_array[0::2, 1::2]
        green2_pixels = input_array[1::2, 0::2]

        a = np.concatenate((red_pixels, green1_pixels), axis=0)
        b = np.concatenate((green2_pixels, blue_pixels), axis=0)
        out = np.concatenate((a, b), axis=1)

    return out


# =========================
# GPIO CLEANUP
# =========================
def cleanup_gpio():
    try:
        GPIO.output(26, GPIO.LOW)
        GPIO.cleanup()
        print("GPIO cleaned on exit")
    except:
        pass


atexit.register(cleanup_gpio)


# =========================
# CNC CONTROLLER
# =========================
class CNCController:
    def __init__(self, port, baudrate, log_func=None):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)

    def wait_for_movement_completion(self, cleaned_line):
        if ('$X' not in cleaned_line) and ('$$' not in cleaned_line) and ('?' not in cleaned_line):
            idle_counter = 0
            time.sleep(0.025)

            while True:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                time.sleep(0.025)

                self.ser.write(str.encode("?\n"))
                time.sleep(0.025)

                grbl_response = self.ser.readline().decode().strip()

                if 'ok' not in grbl_response.lower():
                    if 'idle' in grbl_response.lower():
                        idle_counter += 1

                if idle_counter > 0:
                    break

                if 'alarm' in grbl_response.lower():
                    raise ValueError(grbl_response)

    def send_command(self, command):
        print(f"> {command.strip()}")

        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        self.wait_for_movement_completion(command)

        out = []
        for _ in range(50):
            time.sleep(0.001)
            response = self.ser.readline().decode().strip()
            out.append(response)
            print(f"< {response}")

            if 'ok' in response:
                break

        return response, out

    def get_current_position(self):
        response, out = self.send_command("? \n")

        MPos = out[0].split('|')[1].split(',')
        MPos[0] = MPos[0].split(':')[1]

        return {
            'x_pos': float(MPos[0]),
            'y_pos': float(MPos[1]),
            'z_pos': float(MPos[2])
        }

    def move_XYZ(self, position, return_position=False):
        command = (
            f"G1 X{position['x_pos']} "
            f"Y{position['y_pos']} "
            f"Z{position['z_pos']} F2500"
        )

        response, _ = self.send_command(command)
        return self.get_current_position() if return_position else response

    def home_grbl(self):
        print("HOMING CNC")
        self.send_command("$H\n")

    def set_up_grbl(self, home=True):
        self.send_command("$X\n")
        self.send_command("?\n")
        if home:
            self.home_grbl()

    def close_connection(self):
        self.ser.close()


# =========================
# THREAD WORKERS
# =========================
class CNCWorker(QThread):
    def __init__(self, cnc, command_type, command_data=None):
        super().__init__()
        self.cnc = cnc
        self.command_type = command_type
        self.command_data = command_data

    def run(self):
        try:
            if self.command_type == "jog":
                self.cnc.move_XYZ(self.command_data)
            elif self.command_type == "home":
                self.cnc.home_grbl()
        except Exception as e:
            print("THREAD ERROR:", e)


class CameraWorker(QThread):
    frame_ready = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        self.running = True

        from picamera2 import Picamera2
        self.picam2 = Picamera2()

        config = self.picam2.create_preview_configuration(
            main={"format": "XBGR8888", "size": (480, 360)},
            raw={"format": "SRGGB12", "size": (4056, 3040)},
            display="main",
            queue=False,
            buffer_count=4
        )

        self.picam2.configure(config)
        self.picam2.start()

    def run(self):
        while self.running:
            frame = self.picam2.capture_array("main")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = frame.shape
            qt_image = QImage(
                frame.data, w, h, ch * w,
                QImage.Format.Format_RGB888
            ).copy()

            self.frame_ready.emit(qt_image)

    def stop(self):
        self.running = False
        try:
            self.picam2.stop()
        except:
            pass
        self.quit()
        self.wait()


class StreamRedirector(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        self.text_written.emit(str(text))

    def flush(self):
        pass


# =========================
# MAIN WINDOW
# =========================
class ModernMainWindow(QMainWindow):

    # =========================
    # INIT
    # =========================
    def __init__(self):
        super().__init__()

        self.SERIAL_PORT = "/dev/ttyUSB0"
        self.BAUD_RATE = 115200
        self.settings_path = "/home/r/rpi_camera_tests/camera_settings.txt"

        self.cnc = None
        self.robot_busy = False
        self.active_threads = []

        self.setup_gpio()
        self.setup_window()
        self.setup_layouts()
        self.setup_camera()
        self.setup_logging()
        self.initialize_serial_connection()

    # =========================
    # SETUP METHODS
    # =========================
    def setup_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(26, GPIO.OUT)
        GPIO.output(26, GPIO.LOW)

    def setup_window(self):
        self.setWindowTitle("MiniMax Controller")
        self.setGeometry(100, 100, 1400, 800)

    def setup_layouts(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.main_layout = QHBoxLayout(central_widget)

        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()

        self.main_layout.addLayout(self.left_layout, 1)
        self.main_layout.addLayout(self.right_layout, 5)

        self.camera_label = QLabel()
        self.camera_label.setMinimumSize(400, 300)
        self.camera_label.setStyleSheet("background-color: black;")

        self.right_layout.addWidget(self.camera_label)

    def setup_camera(self):
        self.camera_thread = CameraWorker()
        self.camera_thread.frame_ready.connect(self.update_camera_view)
        self.camera_thread.start()

    def setup_logging(self):
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        self.left_layout.addWidget(self.log_text)

        self.stdout_redirector = StreamRedirector()
        self.stdout_redirector.text_written.connect(self.append_log)

        sys.stdout = self.stdout_redirector
        sys.stderr = self.stdout_redirector

    # =========================
    # CNC CONNECTION
    # =========================
    def initialize_serial_connection(self):
        try:
            self.print_with_timestamp("Connecting to GRBL...")
            self.cnc = CNCController(self.SERIAL_PORT, self.BAUD_RATE)
            self.print_with_timestamp("Connected.")

        except Exception as e:
            traceback.print_exc()
            self.print_with_timestamp(f"Connection failed: {e}")
            self.cnc = None

    # =========================
    # CAMERA
    # =========================
    def update_camera_view(self, image):
        pixmap = QPixmap.fromImage(image)
        self.camera_label.setPixmap(pixmap)

    # =========================
    # LOGGING
    # =========================
    def print_with_timestamp(self, text):
        t = time.strftime("%H:%M:%S")
        print(t, '-', text)

    def append_log(self, text):
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(text)

    # =========================
    # CLEANUP
    # =========================
    def closeEvent(self, event):
        try:
            GPIO.cleanup()
        except:
            pass

        try:
            if self.camera_thread:
                self.camera_thread.stop()
        except:
            pass

        try:
            if self.cnc:
                self.cnc.close_connection()
        except:
            pass

        event.accept()


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = ModernMainWindow()
    window.show()

    sys.exit(app.exec())

