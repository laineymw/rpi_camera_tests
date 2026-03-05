import sys
import time
import serial

from PySide6.QtCore import (
    QObject, Signal, Slot,
    Qt, QTimer, QThread
)
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel,
    QPushButton, QVBoxLayout,
    QGridLayout, QDoubleSpinBox
)

from picamera2 import Picamera2
import libcamera

class CNCController:
    def __init__(self, port, baudrate):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)

    def send_command(self, command):
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write((command + "\n").encode())

        while True:
            response = self.ser.readline().decode().strip()
            if "ok" in response.lower():
                break

    def get_current_position(self):
        self.ser.write("?\n".encode())
        response = self.ser.readline().decode().strip()

        try:
            parts = response.split("|")[1].split(",")
            x = float(parts[0].split(":")[1])
            y = float(parts[1])
            z = float(parts[2])
            return {"x_pos": x, "y_pos": y, "z_pos": z}
        except:
            return {"x_pos": 0, "y_pos": 0, "z_pos": 0}

    def move_XYZ(self, pos):
        cmd = f"G1 X{pos['x_pos']} Y{pos['y_pos']} Z{pos['z_pos']} F2500"
        print("move xyz")
        self.send_command(cmd)

    def home_grbl(self):
        self.send_command("$H")

    def set_up_grbl(self):
        self.send_command("$X")

    def close_connection(self):
        self.ser.close()


class CNCWorker(QObject):
    position_updated = Signal(dict)
    finished = Signal()

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.cnc = None

    @Slot()
    def initialize(self):
        self.cnc = CNCController(self.port, self.baudrate)
        self.cnc.set_up_grbl()

    @Slot(str, object)
    def jog(self, axis, step):
        if self.cnc is None:
            return

        pos = self.cnc.get_current_position()

        if axis == "X":
            pos["x_pos"] += float(step)
        elif axis == "Y":
            pos["y_pos"] += float(step)
        elif axis == "Z":
            pos["z_pos"] += float(step)

        self.cnc.move_XYZ(pos)
        self.position_updated.emit(pos)

    @Slot()
    def home(self):
        if self.cnc is None:
            return

        self.cnc.home_grbl()
        pos = self.cnc.get_current_position()
        self.position_updated.emit(pos)
    
    @Slot()
    def unlock(self):
        if self.cnc is None:
            return

        self.cnc.set_up_grbl()
        pos = self.cnc.get_current_position()
        self.position_updated.emit(pos)

    @Slot()
    def stop(self):
        if self.cnc:
            self.cnc.close_connection()
        self.finished.emit()


class ThreadedGUI(QWidget):
    jog_signal = Signal(str, object)
    home_signal = Signal()
    unlock_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CNC + Camera (Threaded)")
        self.resize(900, 700)

        # ---------------- CAMERA ----------------
        self.picam2 = Picamera2()
        config = self.picam2.create_preview_configuration(
            main={"format": "BGR888", "size": (640, 480)}
        )
        config["transform"] = libcamera.Transform(hflip=1, vflip=1)
        self.picam2.configure(config)
        self.picam2.start()

        # ---------------- CNC THREAD ----------------
        self.thread = QThread()
        self.worker = CNCWorker("/dev/ttyUSB0", 115200)

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.initialize)

        self.jog_signal.connect(self.worker.jog)
        self.home_signal.connect(self.worker.home)
        self.unlock_signal.connect(self.worker.unlock)

        self.worker.position_updated.connect(self.update_position)

        self.thread.start()

        # ---------------- UI ----------------
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)

        self.position_label = QLabel("X: 0  Y: 0  Z: 0")

        self.step = QDoubleSpinBox()
        self.step.setRange(0.01, 100)
        self.step.setValue(1.0)
        self.step.setSingleStep(0.1)

        btn_xp = QPushButton("X+")
        btn_xm = QPushButton("X-")
        btn_yp = QPushButton("Y+")
        btn_ym = QPushButton("Y-")
        btn_zp = QPushButton("Z+")
        btn_zm = QPushButton("Z-")
        btn_home = QPushButton("Home")
        btn_unlock = QPushButton("Unlock")

        btn_xp.clicked.connect(lambda: self.send_jog("X", +1))
        btn_xm.clicked.connect(lambda: self.send_jog("X", -1))
        btn_yp.clicked.connect(lambda: self.send_jog("Y", +1))
        btn_ym.clicked.connect(lambda: self.send_jog("Y", -1))
        btn_zp.clicked.connect(lambda: self.send_jog("Z", +1))
        btn_zm.clicked.connect(lambda: self.send_jog("Z", -1))
        btn_home.clicked.connect(lambda: self.home_signal.emit())
        btn_unlock.clicked.connect(lambda: self.unlock_signal.emit())

        grid = QGridLayout()
        grid.addWidget(btn_zp, 0, 0, 1, 2)
        grid.addWidget(btn_yp, 1, 0, 1, 2)
        grid.addWidget(btn_xm, 2, 0)
        grid.addWidget(btn_xp, 2, 1)
        grid.addWidget(btn_ym, 3, 0, 1, 2)
        grid.addWidget(btn_zm, 4, 0, 1, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.preview)
        layout.addWidget(self.position_label)
        layout.addWidget(self.step)
        layout.addLayout(grid)
        layout.addWidget(btn_home)
        layout.addWidget(btn_unlock)

        self.setLayout(layout)

        # ---------------- CAMERA TIMER ----------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_preview)
        self.timer.start(30)

    # ---------------- CAMERA ----------------

    def update_preview(self):
        frame = self.picam2.capture_array()
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, 3*w, QImage.Format_BGR888)
        self.preview.setPixmap(QPixmap.fromImage(image))

    # ---------------- CNC ----------------

    def send_jog(self, axis, direction):
        step = float(self.step.value()) * float(direction)
        self.jog_signal.emit(axis, step)

    def update_position(self, pos):
        self.position_label.setText(
            f"X: {pos['x_pos']:.2f}  "
            f"Y: {pos['y_pos']:.2f}  "
            f"Z: {pos['z_pos']:.2f}"
        )

    # ---------------- CLEANUP ----------------

    def closeEvent(self, event):
        self.timer.stop()
        self.picam2.stop()

        self.worker.stop()
        self.thread.quit()
        self.thread.wait()

        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ThreadedGUI()
    window.show()
    sys.exit(app.exec())

