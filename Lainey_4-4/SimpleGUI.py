import sys, time, serial
from PySide6.QtCore import Qt, QTimer
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
        import re
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)

    def wait_for_movement_completion(self,cleaned_line):

        # print("waiting on: " + str(cleaned_line))

        if ('$X' not in cleaned_line) and ('$$' not in cleaned_line) and ('?' not in cleaned_line):
            idle_counter = 0
            time.sleep(0.025)
            while True:
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()
                time.sleep(0.025)
                command = str.encode("?"+ "\n") 
                self.ser.write(command)
                time.sleep(0.025)
                grbl_out = self.ser.readline().decode().strip()
                grbl_response = grbl_out.strip()

                if 'ok' not in grbl_response.lower():  
                    if 'idle' in grbl_response.lower():
                        idle_counter += 1
                    else:
                        if grbl_response != '':
                            pass
                            # print(grbl_response)
                if idle_counter == 1 or idle_counter == 2:
                    # print(grbl_response)
                    pass
                if idle_counter > 3:
                    break
                if 'alarm' in grbl_response.lower():
                    raise ValueError(grbl_response)

    def send_command(self, command):
        self.ser.reset_input_buffer() # flush the input and the output
        self.ser.reset_output_buffer()
        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        CNCController.wait_for_movement_completion(self,command)
        out = []
        for i in range(50):
            time.sleep(0.001)
            response = self.ser.readline().decode().strip()
            time.sleep(0.001)
            out.append(response)
            if 'error' in response.lower():
                print('error--------------------------------------------------')
            if 'ok' in response:
                break
            # print(response)
        return response, out
   
    def get_current_position(self):

        command = "? " + "\n"
        response, out = CNCController.send_command(self,command)
        MPos = out[0] # get the idle output
        MPos = MPos.split('|')[1] # get the specific output
        MPos = MPos.split(',')
        MPos[0] = MPos[0].split(':')[1]

        position = dict()

        position['x_pos'] = float(MPos[0])
        position['y_pos'] = float(MPos[1])
        position['z_pos'] = float(MPos[2])

        return position
   
    def move_XY_at_Z_travel(self, position, z_travel_height):

        current_position = CNCController.get_current_position(self)

        if round(float(current_position['z_pos']),1) != float(z_travel_height):
            #### go to z travel height
            # command = "G0 z" + str(z_travel_height) + " " + "\n"
            command = "G1 z" + str(z_travel_height) + " F2500" #+ "\n"
            response, out = CNCController.send_command(self,command)
       
        # print('moving to XY')
        # command = 'G0 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos'])
        command = 'G1 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' F2500'
        response, out = CNCController.send_command(self,command)
        ##### move z
        # print('moving to Z')
        # command = 'G0 ' + 'Z' + str(position['z_pos'])
        command = 'G1 ' + 'Z' + str(position['z_pos']) + ' F2500'
        response, out = CNCController.send_command(self,command)

        return CNCController.get_current_position(self)
   
    def move_XYZ(self, position, return_position = False):

        ##### move xyz
        # print('moving to XYZ')
        # command = 'G0 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' ' + 'Z' + str(position['z_pos'])
        command = 'G1 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' ' + 'Z' + str(position['z_pos']) + ' F2500'
        response, out = CNCController.send_command(self,command)

        if return_position:
            return CNCController.get_current_position(self)
        else:
            return response
   
    def home_grbl(self):
        print("HOMING CNC")
        command = "$H"+ "\n"
        response, out = CNCController.send_command(self,command)
   
    def set_up_grbl(self, home = True):
        # unlock
        command = "$X"+ "\n"
        response, out = CNCController.send_command(self,command)

        command = "?"+ "\n"
        response, out = CNCController.send_command(self,command)

        if home:
            CNCController.home_grbl(self)

    def close_connection(self):
        self.ser.close()


class SimpleGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CNC + Camera")

        # ---------------- CNC ----------------
        self.cnc = CNCController("/dev/ttyUSB0", 115200)
        self.cnc.set_up_grbl(home=False)

        # ---------------- CAMERA ----------------
        self.picam2 = Picamera2()
        self.configure_camera()
        self.picam2.start()

        # ---------------- UI ----------------
        self.preview = QLabel()
        self.preview.setMinimumSize(640, 480)
        self.preview.setAlignment(Qt.AlignCenter)

        self.position_label = QLabel("X: 0  Y: 0  Z: 0")

        self.step = QDoubleSpinBox()
        self.step.setRange(0.01, 100)
        self.step.setValue(1.0)

        # Buttons
        btn_xp = QPushButton("X+")
        btn_xm = QPushButton("X-")
        btn_yp = QPushButton("Y+")
        btn_ym = QPushButton("Y-")
        btn_zp = QPushButton("Z+")
        btn_zm = QPushButton("Z-")
        btn_home = QPushButton("Home")

        # Connect buttons
        btn_xp.clicked.connect(lambda: self.jog("X", +1))
        btn_xm.clicked.connect(lambda: self.jog("X", -1))
        btn_yp.clicked.connect(lambda: self.jog("Y", +1))
        btn_ym.clicked.connect(lambda: self.jog("Y", -1))
        btn_zp.clicked.connect(lambda: self.jog("Z", +1))
        btn_zm.clicked.connect(lambda: self.jog("Z", -1))
        btn_home.clicked.connect(self.home)

        # Layout
        grid = QGridLayout()
        grid.addWidget(btn_zp, 0, 0, 1, 2)
        grid.addWidget(btn_yp, 1, 0, 1, 2)
        grid.addWidget(btn_xm, 2, 1)
        grid.addWidget(btn_xp, 2, 0)
        grid.addWidget(btn_ym, 3, 0, 1, 2)
        grid.addWidget(btn_zm, 4, 0, 1, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.preview)
        layout.addWidget(self.position_label)
        layout.addWidget(self.step)
        layout.addLayout(grid)
        layout.addWidget(btn_home)

        self.setLayout(layout)

        # ---------------- TIMER ----------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_preview)
        self.timer.start(33)

    # ---------------- CAMERA ----------------

    def configure_camera(self):
        config = self.picam2.create_preview_configuration(
            main={"format": "BGR888", "size": (640, 480)}
        )
        config["transform"] = libcamera.Transform(hflip=1, vflip=1)
        self.picam2.configure(config)

    def update_preview(self):
        frame = self.picam2.capture_array()
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, 3*w, QImage.Format_BGR888)
        self.preview.setPixmap(QPixmap.fromImage(image))

        # Update position display
        try:
            pos = self.cnc.get_current_position()
            self.position_label.setText(
                f"X: {pos['x_pos']:.2f}  "
                f"Y: {pos['y_pos']:.2f}  "
                f"Z: {pos['z_pos']:.2f}"
            )
        except:
            pass

    # ---------------- CNC ----------------

    def jog(self, axis, direction):
        step = self.step.value() * direction
        pos = self.cnc.get_current_position()

        if axis == "X":
            pos["x_pos"] += step
        elif axis == "Y":
            pos["y_pos"] += step
        elif axis == "Z":
            pos["z_pos"] += step

        self.cnc.move_XYZ(pos)

    def home(self):
        self.cnc.home_grbl()

    # ---------------- CLEANUP ----------------

    def closeEvent(self, event):
        self.timer.stop()
        self.picam2.stop()
        self.cnc.close_connection()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = SimpleGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()