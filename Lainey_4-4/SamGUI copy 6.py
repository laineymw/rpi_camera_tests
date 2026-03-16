# add ? button that gets position
# make arrowkeys work
# maybe make example autofocus or take picture
# add time stamp get position to worker thread
# make the delay after pressing button less long

# make take picture do raw image
# make it center after homing

###################################################
#   Log of what I did Thursday 3/5/26
#   Made wait for completion only need 1 idle
#   Tried to break it, fine as long as dont hit limit switch
#   Sam wants to be able to go to one spot and take picture
#   Tried to add a log of everything sent to and recieved from GRBL
#   It took a long time and went badly
#   At the end of the day I got rid of most of the log structure
#   Now the log is there but does not populate
#   Todo: make log populate (maybe not through CNC controller send command definition because that went wrong)
#   Todo: do what Sam originally wanted and make it take a picture at a spot
###################################################


import sys, time, serial, RPi.GPIO as GPIO, cv2, datetime, traceback
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
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject

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

        GPIO.output(26, GPIO.LOW)
        GPIO.cleanup()

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
        config = self.picam2.create_preview_configuration()
        self.picam2.configure(config)
        self.picam2.start()

    def run(self):
        while self.running:
            frame = self.picam2.capture_array()

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
        self.picam2.stop()
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
       
        left_layout.addWidget(self.log_text)
       
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
       
        '''
        # Toggle Option 2
        toggle2_layout = QVBoxLayout()
        self.toggle_label2 = QLabel("Option 2:")
        self.toggle_switch2 = QCheckBox()
        self.toggle_switch2.setChecked(False)
        self.toggle_switch2.stateChanged.connect(self.toggle_option2)
        toggle2_layout.addWidget(self.toggle_label2)
        toggle2_layout.addWidget(self.toggle_switch2)
        toggle2_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
       
        # Toggle Option 3
        toggle3_layout = QVBoxLayout()
        self.toggle_label3 = QLabel("Option 3:")
        self.toggle_switch3 = QCheckBox()
        self.toggle_switch3.setChecked(False)
        self.toggle_switch3.stateChanged.connect(self.toggle_option3)
        toggle3_layout.addWidget(self.toggle_label3)
        toggle3_layout.addWidget(self.toggle_switch3)
        toggle3_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        '''

        toggle_layout.addLayout(toggle1_layout)
        toggle_layout.addWidget(self.step)
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
            frame = self.camera_thread.picam2.capture_array()

            # create timestamp filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"image_{timestamp}.jpg"

            cv2.imwrite(filename, frame)

            self.print_with_timestamp(f"Saved image: {filename}")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Modern Terminal App")
    app.setApplicationVersion("1.0")
   
    window = ModernMainWindow()
    window.show()
    sys.exit(app.exec())

