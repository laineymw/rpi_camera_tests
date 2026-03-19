# add ? button that gets position
# make arrowkeys work
# make sliders update even when in automode
# add spots to type in exact gain and exposure values
# maybe put exposure values into fractions of seconds
# turn off auto white balance
# system locks when you hit a limit switch

import sys, time, serial, RPi.GPIO as GPIO, cv2, datetime, traceback, numpy as np, atexit, math
from PyQt6.QtGui import QTextCursor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QGridLayout,
    QInputDialog,
    QCheckBox,
    QLabel,
    QFrame,
    QDoubleSpinBox, 
    QSizePolicy,
    QSlider,
    QSpinBox,
    QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject


def process_raw(input_array,R = False, G = False, G1 = False, G2 = False, B = False, RGB = True, RGB2 = False, rgb_or_bgr = True, mono = False):
    if 'uint16' not in str(input_array.dtype):
        input_array = input_array.view(np.uint16)
        if mono:
            return input_array

    if R or G or B or G1 or G2 or RGB2:
        RGB = False

    if RGB: # return an rgb array
        blue_pixels = input_array[0::2,0::2]
        red_pixels = input_array[1::2,1::2]
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        avg_green = ((green1_pixels&green2_pixels) + (green1_pixels^green2_pixels)/2).astype(np.uint16)

        if rgb_or_bgr:
            out = np.asarray([red_pixels,avg_green,blue_pixels]).transpose(1,2,0)
        else:
            out = np.asarray([blue_pixels,avg_green,red_pixels]).transpose(1,2,0)
    if R: # just the red pixels
        out = input_array[1::2,1::2]
    if G: # just the green pixels (averaged)
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        out = ((green1_pixels&green2_pixels) + (green1_pixels^green2_pixels)/2).astype(np.uint16)
    if G1: # just the green 1 pixels
        out = input_array[0::2,1::2]
    if G2: # just the green 2 pixels
        out = input_array[1::2,0::2]
    if B: # just blue pixels
        out = input_array[0::2,0::2]
    if RGB2: # 2x2 array of the pixel values
        blue_pixels = input_array[0::2,0::2]
        red_pixels = input_array[1::2,1::2]
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        a = np.concatenate((red_pixels,green1_pixels),axis = 0)
        b = np.concatenate((green2_pixels,blue_pixels ), axis = 0)
        out = np.concatenate((a,b),axis = 1)

    return out

def cleanup_gpio():
    try:
        GPIO.output(26, GPIO.LOW)
        GPIO.cleanup()
        print("GPIO cleaned on exit")
    except:
        pass

atexit.register(cleanup_gpio)

class CNCController:
    def __init__(self, port, baudrate, log_func=None):
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
                if idle_counter > 0:
                    break
                if 'alarm' in grbl_response.lower():
                    raise ValueError(grbl_response)

    def send_command(self, command):
        #self.ser.reset_input_buffer() # flush the input and the output
        #self.ser.reset_output_buffer()
        print(f"> {command.strip()}")

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
            print (f"< {response}")
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
        #print('moving to XYZ')
        command = 'G0 ' + 'X' + str(position['x_pos']) + ' ' + 'Y' + str(position['y_pos']) + ' ' + 'Z' + str(position['z_pos'])
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
        
    def CloseEvent (self, event):

        if self.cnc is not None:
            self.cnc.close_connection()

        if hasattr(self, "camera_thread"):
            self.camera_thread.stop()

        event.accept()

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
        # config = self.picam2.create_preview_configuration()
        cam_config = self.picam2.create_preview_configuration(
            main= {"format": "XBGR8888", "size": (480,360)},#(int(2028/2),int(1520/2))}, #(480,360)},
            # lores = {"format": "XBGR8888","size":(480,360)},# (507,380),(480,360)
            raw={"format": "SRGGB12", "size": (4056,3040)},#(4056,3040)},(2028,1520),(2028,1080)
            display = "main" ,queue=False ,buffer_count=4 #, SRGGB12_CSI2P
        )
        self.picam2.configure(cam_config)
        self.picam2.start()

    def run(self):
        while self.running:
            frame = self.picam2.capture_array("main")

            # Convert to RGB (OpenCV uses BGR)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = frame.shape
            bytes_per_line = ch * w

            qt_image = QImage(
                frame.data,
                w,
                h,
                bytes_per_line,
                QImage.Format.Format_RGB888,
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


class ModernMainWindow(QMainWindow):
    def initialize_serial_connection(self):
        try:
            self.print_with_timestamp("Connecting to GRBL...")
            self.cnc = CNCController(self.SERIAL_PORT, self.BAUD_RATE)
            self.print_with_timestamp("Serial connection established.")

            # Wake up GRBL
            self.cnc.ser.write(b"\r\n\r\n")
            time.sleep(2)
            self.cnc.ser.flushInput()

            self.print_with_timestamp("GRBL ready.")

            self.print_with_timestamp("Unlocking GRBL...")
            self.cnc.send_command("$X\n")

            self.print_with_timestamp("Starting homing cycle...")
            #self.cnc.home_grbl()
            self.print_with_timestamp("Homing complete.")

        except Exception as e:
            traceback.print_exc()
            self.print_with_timestamp(f"Failed to connect or home: {e}")
            self.cnc = None

    def __init__(self):
        super().__init__()
        self.SERIAL_PORT = "/dev/ttyUSB0"
        self.BAUD_RATE = 115200
        self.settings_path = "/home/r/rpi_camera_tests/camera_settings.txt"
        self.cnc = None
        self.robot_busy = False

        self.auto_update_timer = QTimer()
        self.auto_update_timer.timeout.connect(self.update_auto_values)
        self.auto_update_timer.start(200)

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(26, GPIO.OUT)
        GPIO.output(26, GPIO.LOW)

        self.setWindowTitle("MiniMax Controller")
        self.setGeometry(100, 100, 1400, 800)

        self.active_threads = []

        # Set modern dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #252538;
                color: #e0e0e0;
                border: 1px solid #3a3a5a;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
            QPushButton {
                background-color: #4a4a6a;
                color: white;
                border: none;
                padding: 10px 15px;
                border-radius: 6px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #5a5a7a;
            }
            QPushButton:pressed {
                background-color: #3a3a5a;
            }
            QCheckBox {
                color: #e0e0e0;
                font-weight: 400;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #5a5a7a;
                border-radius: 4px;
                background-color: #252538;
            }
            QCheckBox::indicator:checked {
                background-color: #6a6a9a;
                border: 2px solid #6a6a9a;
            }
            QCheckBox::indicator:unchecked {
                background-color: #252538;
            }
            QLabel {
                color: #e0e0e0;
                font-weight: 500;
            }
            QFrame {
                background-color: #252538;
                border-radius: 8px;
                border: 1px solid #3a3a5a;
            }
        """)
       
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 5)
        

        # Camera
        self.camera_label = QLabel()
        self.camera_label.setMinimumSize(400, 300)
        self.camera_label.setStyleSheet("background-color: black;")

        self.camera_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        right_layout.addWidget(self.camera_label, 4)
       
        # Header
        header_frame = QFrame()
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 15, 15, 15)
       
        title_label = QLabel("MiniMax Controller")
        title_label.setStyleSheet("font-size: 20px; font-weight: 600; color: #6a6aff;")
       
        header_layout.addWidget(title_label)
        header_layout.addStretch()
       
        left_layout.addWidget(header_frame)
       
        # Output display area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(250)
        self.log_text.setPlaceholderText("Output will appear here...")
       
        # Custom scrollbar styling
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #252538;
                color: #e0e0e0;
                border: 1px solid #3a3a5a;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
            QTextEdit QScrollBar:vertical {
                background: #252538;
                width: 12px;
                margin: 0px;
            }
            QTextEdit QScrollBar::handle:vertical {
                background: #4a4a6a;
                border-radius: 6px;
                min-height: 20px;
            }
            QTextEdit QScrollBar::handle:vertical:hover {
                background: #5a5a7a;
            }
        """)
       
        # Create container for log + exposure controls
        log_container = QHBoxLayout()

        # ---- LOG ----
        log_container.addWidget(self.log_text, 4)

        # ---- EXPOSURE CONTROL PANEL ----
        exposure_frame = QFrame()
        exposure_layout = QVBoxLayout(exposure_frame)
        exposure_layout.setContentsMargins(10, 10, 10, 10)

        # Label
        self.exposure_label = QLabel("Exposure")
        self.exposure_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Toggle (Auto Exposure)
        self.exposure_toggle = QCheckBox("Auto")
        self.exposure_toggle.setChecked(True)
        self.exposure_toggle.stateChanged.connect(self.toggle_exposure_mode)

        # Exposure table
        self.exposure_values = [1/(2**i) for i in range(1, 11)]  
        # [1/2, 1/4, ..., 1/1024]
        self.exposure_us_values = [int(s * 1_000_000) for s in self.exposure_values]

        # Vertical slider
        self.exposure_slider = QSlider(Qt.Orientation.Vertical)
        self.exposure_slider.setMinimum(0)
        self.exposure_slider.setMaximum(len(self.exposure_us_values) - 1)
        self.exposure_slider.setValue(4) 
        self.exposure_slider.setEnabled(False)   # disabled when auto is ON
        self.exposure_slider.valueChanged.connect(self.update_exposure)

        self.exposure_input = QSpinBox()
        self.exposure_input.setRange(1, 1_000_000)  # microseconds
        self.exposure_input.setSuffix(" us")
        self.exposure_input.setEnabled(False)

        self.exposure_input.valueChanged.connect(self.set_exposure_from_input)

        # Add to layout
        exposure_layout.addWidget(self.exposure_label)
        exposure_layout.addWidget(self.exposure_toggle)
        exposure_layout.addWidget(self.exposure_slider)
        exposure_layout.addWidget(self.exposure_input)

        log_container.addWidget(exposure_frame, 1)
        left_layout.addLayout(log_container)

       
        # Control buttons
        button_frame = QFrame()
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(10, 10, 10, 10)
        button_layout.setSpacing(10)
       
        self.clear_button = QPushButton("Clear Output")
        self.clear_button.clicked.connect(self.clear_output)
       
        self.example_button = QPushButton("Run Example")
        self.example_button.clicked.connect(self.run_example)
       
        self.input_button = QPushButton("Get Input")
        self.input_button.clicked.connect(self.get_user_input)
       
        self.center_button = QPushButton("Go to Center")
        self.center_button.clicked.connect(self.move_center)

        self.home_button = QPushButton("Home CNC")
        self.home_button.clicked.connect(self.safe_home)

        self.picture_button = QPushButton("Take Pic")
        self.picture_button.clicked.connect(self.take_pic)

        self.step = QDoubleSpinBox()
        self.step.setRange(0.01, 100)
        self.step.setValue(1.0)
            
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.example_button)
        button_layout.addWidget(self.input_button)
        button_layout.addWidget(self.center_button)
        button_layout.addWidget(self.home_button)
        button_layout.addWidget(self.picture_button)
        button_layout.addStretch()
       
        left_layout.addWidget(button_frame)
       
        # Toggle switches
        toggle_frame = QFrame()
        toggle_layout = QHBoxLayout(toggle_frame)
        toggle_layout.setContentsMargins(15, 15, 15, 15)
        toggle_layout.setSpacing(20)
       
        # Toggle LED
        toggle1_layout = QVBoxLayout()
        self.toggle_label1 = QLabel("LED:")
        self.toggle_switch1 = QCheckBox()
        self.toggle_switch1.setChecked(False)
        self.toggle_switch1.stateChanged.connect(self.toggle_option1)
        toggle1_layout.addWidget(self.toggle_label1)
        toggle1_layout.addWidget(self.toggle_switch1)
        toggle1_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
       
        # Analog Gain Slider
        self.gain_label = QLabel("Analog Gain: 1.0")

        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setMinimum(0)
        self.gain_slider.setMaximum(51)
        self.gain_slider.setValue(0)

        self.gain_slider.valueChanged.connect(self.update_gain)

        toggle_layout.addLayout(toggle1_layout)

        self.gain_input = QDoubleSpinBox()
        self.gain_input.setRange(0.0, 50.0)  # dB
        self.gain_input.setSingleStep(0.5)
        self.gain_input.setSuffix(" dB")
        self.gain_input.setEnabled(False)

        self.gain_input.valueChanged.connect(self.set_gain_from_input)

        toggle_layout.addWidget(self.gain_input)

        # Step size control
        step_layout = QVBoxLayout()

        self.step_label = QLabel("Step Size")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        step_layout.addWidget(self.step_label)
        step_layout.addWidget(self.step)

        toggle_layout.addLayout(step_layout)

        toggle_layout.addWidget(self.gain_label)
        toggle_layout.addWidget(self.gain_slider)
        #toggle_layout.addLayout(toggle2_layout)
        #toggle_layout.addLayout(toggle3_layout)
        toggle_layout.addStretch()
       
        left_layout.addWidget(toggle_frame)
       
        # Arrow buttons grid
        arrow_frame = QFrame()
        arrow_layout = QGridLayout(arrow_frame)
        arrow_layout.setContentsMargins(15, 15, 15, 15)
        arrow_layout.setSpacing(10)
       
        self.up_button = QPushButton("↑ Up")
        self.up_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.up_button.clicked.connect(lambda: self.jog("Z", 1))
       
        self.down_button = QPushButton("↓ Down")
        self.down_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.down_button.clicked.connect(lambda: self.jog("Z", -1))
       
        self.left_button = QPushButton("← Left")
        self.left_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.left_button.clicked.connect(lambda: self.jog("X", 1))
       
        self.right_button = QPushButton("→ Right")
        self.right_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.right_button.clicked.connect(lambda: self.jog("X", -1))
       
        self.forward_button = QPushButton("Forward")
        self.forward_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.forward_button.clicked.connect(lambda: self.jog("Y", -1))
       
        self.backwards_button = QPushButton("Backward")
        self.backwards_button.setStyleSheet("font-size: 14px; padding: 10px;")
        self.backwards_button.clicked.connect(lambda: self.jog("Y", 1))

        arrow_layout.addWidget(self.up_button, 0, 0)
        arrow_layout.addWidget(self.forward_button, 1, 1)
        arrow_layout.addWidget(self.right_button, 1, 2)
        arrow_layout.addWidget(self.down_button, 0, 2)
        arrow_layout.addWidget(self.backwards_button, 0, 1)
        arrow_layout.addWidget(self.left_button, 1, 0)
       
        left_layout.addWidget(arrow_frame)

        # Initialize stream redirector
        self.initialize_serial_connection()
        self.stdout_redirector = StreamRedirector()
        self.stdout_redirector.text_written.connect(self.append_log)

        sys.stdout = self.stdout_redirector
        sys.stderr = self.stdout_redirector
       
        # Add initial message
        self.log_text.append("Application initialized. Toggle options and interact with controls.\n\n")
       
        # Store toggle states
        self.option1_enabled = False
        self.option2_enabled = False
        self.option3_enabled = False

        # camera
        self.camera_thread = CameraWorker()
        self.camera_thread.frame_ready.connect(self.update_camera_view)
        self.camera_thread.start()

    # camera
    def update_camera_view(self, image):
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.camera_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.camera_label.setPixmap(scaled)
    
    def format_exposure(self, exposure_us):
        if exposure_us is None or exposure_us <= 0:
            return "?"

        seconds = exposure_us / 1_000_000

        if seconds >= 1:
            # Show whole seconds (or decimal if needed)
            if seconds.is_integer():
                return f"{int(seconds)}"
            else:
                return f"{seconds:.1f}"
        else:
            # Convert to fraction 1/x
            denom = round(1 / seconds)

            # Clamp to reasonable camera-style values
            return f"1/{denom}"

    def get_nearest_exposure_index(self, exposure_us):
        return min(
            range(len(self.exposure_us_values)),
            key=lambda i: abs(self.exposure_us_values[i] - exposure_us)
        )

    def update_gain(self, db_value):
        if self.exposure_toggle.isChecked():
            return

        try:
            # gain = 10 ** (db_value / 20)
            gain = db_value

            self.gain_slider.blockSignals(True)
            self.gain_input.blockSignals(True)
            self.gain_input.setValue(db_value)

            self.camera_thread.picam2.set_controls({
                "AnalogueGain": gain
            })

            self.gain_label.setText(f"Gain: {db_value} dB")

        except Exception as e:
            self.print_with_timestamp(f"Gain error: {e}")

        finally:
            self.gain_slider.blockSignals(False)
            self.gain_input.blockSignals(False)

    def gain_to_db(self, gain):
        return int(round(20 * math.log10(gain)))

    def toggle_exposure_mode(self, state):
        auto_enabled = self.exposure_toggle.isChecked()

        try:
            if auto_enabled:
                # ---- ENABLE AUTO ----
                self.camera_thread.picam2.set_controls({
                    "AeEnable": True
                })

                # Disable sliders (read-only mode)
                self.exposure_slider.setEnabled(False)
                self.gain_slider.setEnabled(False)

                self.exposure_input.setEnabled(False)
                self.gain_input.setEnabled(False)

                self.exposure_label.setText("Exposure\nAuto")
                self.gain_label.setText("Analog Gain (Auto)")

                self.print_with_timestamp("Auto Exposure + Gain Enabled")

            else:
                # ---- SWITCH TO MANUAL ----
                self.exposure_input.setEnabled(True)
                self.gain_input.setEnabled(True)
                # 🔥 IMPORTANT: grab current auto values so there's no jump
                metadata = self.camera_thread.picam2.capture_metadata()

                exposure = metadata.get("ExposureTime", None)
                gain = metadata.get("AnalogueGain", None)

                # Disable AE FIRST
                self.camera_thread.picam2.set_controls({
                    "AeEnable": False
                })

                controls = {}

                if exposure is not None:
                    idx = self.get_nearest_exposure_index(exposure)

                    self.exposure_slider.blockSignals(True)
                    self.exposure_slider.setValue(idx)
                    self.exposure_slider.blockSignals(False)

                    self.exposure_label.setText(
                        f"Exposure\n{self.format_exposure(self.exposure_us_values[idx])}"
                    )

                if gain is not None:
                    db_val = self.gain_to_db(gain)

                    self.gain_slider.blockSignals(True)
                    self.gain_slider.setValue(db_val)
                    self.gain_slider.blockSignals(False)

                    self.gain_label.setText(f"Gain: {db_val} dB")

                # Apply locked-in values
                if controls:
                    self.camera_thread.picam2.set_controls(controls)

                # Enable sliders (manual control)
                self.exposure_slider.setEnabled(True)
                self.gain_slider.setEnabled(True)

                self.print_with_timestamp("Manual Exposure + Gain Enabled")

        except Exception as e:
            self.print_with_timestamp(f"Exposure toggle error: {e}")

    def update_exposure(self, index):
        if self.exposure_toggle.isChecked():
            return

        try:
            
            exposure_time = self.exposure_us_values[index]

            self.exposure_slider.blockSignals(True)
            self.exposure_input.blockSignals(True)
            self.exposure_input.setValue(exposure_time)

            self.camera_thread.picam2.set_controls({
                "ExposureTime": exposure_time
            })

            self.exposure_label.setText(f"Exposure\n{self.format_exposure(exposure_time)}")

        except Exception as e:
            self.print_with_timestamp(f"Exposure error: {e}")

        finally:
            self.exposure_slider.blockSignals(False)
            self.exposure_input.blockSignals(False)

    def set_exposure_from_input(self, value):
        if self.exposure_toggle.isChecked():
            return

        try:
            self.camera_thread.picam2.set_controls({
                "ExposureTime": int(value)
            })

            self.exposure_label.setText(f"Exposure\n{self.format_exposure(value)}")

            # Sync slider to match typed value
            idx = self.get_nearest_exposure_index(value)

            self.exposure_slider.blockSignals(True)
            self.exposure_slider.setValue(idx)
            self.exposure_slider.blockSignals(False)

        except Exception as e:
            self.print_with_timestamp(f"Exposure input error: {e}")

    def set_gain_from_input(self, db_value):
        if self.exposure_toggle.isChecked():
            return

        try:
            gain = db_value  # same logic you're already using

            self.camera_thread.picam2.set_controls({
                "AnalogueGain": gain
            })

            self.gain_label.setText(f"Gain: {db_value} dB")

            # Sync slider
            self.gain_slider.blockSignals(True)
            self.gain_slider.setValue(int(db_value))
            self.gain_slider.blockSignals(False)

        except Exception as e:
            self.print_with_timestamp(f"Gain input error: {e}")
        
    def jog(self, axis, direction):

        if self.robot_busy:
            return

        self.robot_busy = True
        self.set_motion_buttons_enabled(False)

        step = self.step.value() * direction
        pos = self.cnc.get_current_position()

        if axis == "X":
            pos["x_pos"] += step
        elif axis == "Y":
            pos["y_pos"] += step
        elif axis == "Z":
            pos["z_pos"] += step

        thread = CNCWorker(self.cnc, "jog", pos)
        self.active_threads.append(thread)

        # When movement finishes → unlock buttons
        thread.finished.connect(self.motion_finished)
        thread.finished.connect(lambda: self.active_threads.remove(thread))
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def safe_home(self):

        if self.robot_busy:
            return 

        self.robot_busy = True
        self.set_motion_buttons_enabled(False)

        self.print_with_timestamp("Starting homing cycle...")

        thread = CNCWorker(self.cnc, "home")
        self.active_threads.append(thread)

        thread.finished.connect(self.motion_finished)
        thread.finished.connect(lambda: self.active_threads.remove(thread))
        thread.finished.connect(thread.deleteLater)

        thread.start()

    def take_pic(self):
        try:

            # capture raw

            array_to_process = self.camera_thread.picam2.capture_array("raw")#,"lores"]) #"main","lores","raw"
            raw_data = process_raw(array_to_process, RGB= True, rgb_or_bgr=False)#, G = True) # RGB = True, 

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"img_{timestamp}"

            # save raw
            tiff_name = f"{base_name}.tiff"
            cv2.imwrite(tiff_name, raw_data)

            # uint16 -> uint8
            #raw_8bit = (raw_data // 256).astype(np.uint8)
            raw_8bit = (raw_data / raw_data.max() * 255).astype(np.uint8)

            # save jpeg
            jpg_name = f"{base_name}.jpg"
            cv2.imwrite(jpg_name, raw_8bit)

            self.print_with_timestamp(f"Saved: {tiff_name} + {jpg_name}")

        except Exception as e:
            self.print_with_timestamp(f"Camera error: {e}")

    def print_with_timestamp(self,input_string):

        t = time.localtime()
        current_time = time.strftime("%H:%M:%S", t)
        print(current_time,'-',input_string)

    def append_log(self, text):
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

   
    def clear_output(self):
        self.log_text.clear()
        self.print_with_timestamp("Output cleared")
   
    def run_example(self):
        self.print_with_timestamp("Starting example with delay...")
        self.print_with_timestamp("This will show delayed output without freezing the GUI")
       
        # Start the delayed sequence
        self.delay_counter = 0
        self.delay_sequence()
   
    def delay_sequence(self):
        if self.delay_counter < 5:
            self.print_with_timestamp(f"Processing step {self.delay_counter + 1}...")
            self.delay_counter += 1
           
            # Use QTimer to schedule the next step after a delay
            # This prevents GUI freezing
            QTimer.singleShot(1000, self.delay_sequence)  # 1 second delay
        else:
            self.print_with_timestamp("Example completed with delays!")
    
    def set_motion_buttons_enabled(self, enabled: bool):
        # Arrow buttons
        self.up_button.setEnabled(enabled)
        self.down_button.setEnabled(enabled)
        self.left_button.setEnabled(enabled)
        self.right_button.setEnabled(enabled)
        self.forward_button.setEnabled(enabled)
        self.backwards_button.setEnabled(enabled)

        # Also lock these
        self.center_button.setEnabled(enabled)
        self.home_button.setEnabled(enabled)


    def motion_finished(self):
        self.robot_busy = False
        self.set_motion_buttons_enabled(True)
    
    def get_user_input(self):
        text, ok = QInputDialog.getText(self, "Send Command to GRBL", "Enter GRBL command:")

        if ok and text:
            command = text.strip()

            # Ensure newline (GRBL requires it)
            if not command.endswith("\n"):
                command += "\n"

            self.print_with_timestamp(f"> {command.strip()}")

            try:
                response, out = self.cnc.send_command(command)

                # Print all returned lines
                for line in out:
                    if line:
                        self.print_with_timestamp(line)

            except Exception as e:
                self.print_with_timestamp(f"Error: {e}")

        else:
            self.print_with_timestamp("No command entered")
   
    def move_center(self):
        if self.robot_busy:
            return 
        
        self.robot_busy = True
        self.set_motion_buttons_enabled(False)

        self.print_with_timestamp("Moving to Center")

        pos = {
            "x_pos": -81,
            "y_pos": -67,
            "z_pos": -17
        }

        thread = CNCWorker(self.cnc, "jog", pos)

        self.active_threads.append(thread)

        thread.finished.connect(self.motion_finished)
        thread.finished.connect(lambda: self.active_threads.remove(thread))
        thread.finished.connect(thread.deleteLater)

        thread.start()
   
    def print_direction(self, direction):
        self.print_with_timestamp(f"Direction command: {direction}")
   
    def toggle_option1(self, state):
        # Using the checkState().value approach that works
        current_state = self.toggle_switch1.checkState().value
        if current_state != 0:
            self.option1_enabled = True
            self.print_with_timestamp("LED turned on")
            GPIO.output(26, GPIO.HIGH)
        else:
            self.option1_enabled = False
            self.print_with_timestamp("LED turned off")
            GPIO.output(26, GPIO.LOW)
   
    def toggle_option2(self, state):
        # Using the checkState().value approach that works
        current_state = self.toggle_switch2.checkState().value
        if current_state != 0:
            self.option2_enabled = True
            self.print_with_timestamp("Option 2 enabled")
        else:
            self.option2_enabled = False
            self.print_with_timestamp("Option 2 disabled")
   
    def toggle_option3(self, state):
        # Using the checkState().value approach that works
        current_state = self.toggle_switch3.checkState().value
        if current_state != 0:
            self.option3_enabled = True
            self.print_with_timestamp("Option 3 enabled")
        else:
            self.option3_enabled = False
            self.print_with_timestamp("Option 3 disabled")
    
    def update_auto_values(self):
        if not self.exposure_toggle.isChecked():
            return  # only update when auto is ON

        try:
            metadata = self.camera_thread.picam2.capture_metadata()

            exposure = metadata.get("ExposureTime", None)
            gain = metadata.get("AnalogueGain", None)

            # ---- UPDATE EXPOSURE SLIDER ----
            if exposure is not None:
                idx = self.get_nearest_exposure_index(exposure)

                self.exposure_slider.blockSignals(True)
                self.exposure_slider.setValue(idx)
                self.exposure_slider.blockSignals(False)

                self.exposure_label.setText(
                    f"Exposure\n{self.format_exposure(self.exposure_us_values[idx])}"
    )

            # ---- UPDATE GAIN SLIDER ----
            if gain is not None:
                db_val = self.gain_to_db(gain)

                self.gain_slider.blockSignals(True)
                self.gain_slider.setValue(db_val)
                self.gain_slider.blockSignals(False)

                self.gain_label.setText(f"Gain: {db_val} dB")

        except Exception as e:
            self.print_with_timestamp(f"Auto update error: {e}")
        
    def closeEvent(self, event):
        print("Closing application...")

        # ---- TURN OFF LED ----
        try:
            GPIO.output(26, GPIO.LOW)
            GPIO.cleanup()
            print("GPIO cleaned up")
        except Exception as e:
            print(f"GPIO cleanup error: {e}")

        # ---- STOP CAMERA THREAD ----
        try:
            if hasattr(self, "camera_thread"):
                self.camera_thread.stop()
                print("Camera stopped")
        except Exception as e:
            print(f"Camera cleanup error: {e}")

        # ---- CLOSE CNC SERIAL ----
        try:
            if self.cnc is not None:
                self.cnc.close_connection()
                print("CNC disconnected")
        except Exception as e:
            print(f"CNC cleanup error: {e}")

        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Modern Terminal App")
    app.setApplicationVersion("1.0")
   
    window = ModernMainWindow()
    window.show()
    sys.exit(app.exec())


