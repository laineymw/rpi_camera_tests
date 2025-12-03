from focus import run_autofocus_at_current_position
from picamera2 import Picamera2, Preview
from pathlib import Path
from datetime import datetime
import time, serial, libcamera, os, cv2
import RPi.GPIO as GPIO
import matplotlib
matplotlib.use('Qt5Agg')   # or 'QtAgg' depending on version
import matplotlib.pyplot as plt

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

# set up serial connection
controller = CNCController(port="/dev/ttyUSB0", baudrate=115200)

# set up camera
tuning_file = Picamera2.load_tuning_file('imx477_scientific.json')#imx477_scientific
picam2 = Picamera2(tuning=tuning_file)

cam_config = picam2.create_preview_configuration(
    main= {"format": "YUV420", "size": (480,360)},
    raw={"format": "SRGGB12", "size": (2028,1520)},
    display = "main"  ,buffer_count=2 
)
cam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(cam_config)

# set up led
GPIO.setmode(GPIO.BCM)
GPIO.setup(26, GPIO.OUT)
GPIO.output(26, GPIO.HIGH)

# start preview
preview_width = int(1920/2)
preview_height = int(1920/2) #640 #int(1080/2)
preview = picam2.start_preview(Preview.QTGL,x=1920-preview_width,y=1, width = preview_width, height = preview_height)
picam2.set_controls({'AnalogueGain':16})
picam2.start()

# set up path for saving
documents = Path.home() / "Documents"
timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
folder_path = documents / f"60mmPlate_{timestamp}"
os.makedirs(folder_path, exist_ok=True)

# home
controller.home_grbl()

# go to position
position = dict()
position['x_pos'] = -82
position['y_pos'] = -69
position['z_pos'] = -6.9
controller.move_XYZ(position)

# rough focus
this_well_coords = controller.get_current_position()
z_height, cap, rough_fscore, z_rough = run_autofocus_at_current_position(
    controller.ser, this_well_coords, picam2,
    autofocus_min_max=[-4, 4], autofocus_delta_z= (1/3)
)
this_well_coords = controller.get_current_position()

# fine focus
this_well_coords = controller.get_current_position()
z_height, cap, smooth_fscore, z_smooth = run_autofocus_at_current_position(
    controller.ser, this_well_coords, picam2,
    autofocus_min_max=[-0.5, 0.3], autofocus_delta_z=0.1
)



# Plot rough vs z_rough and smooth vs z_smooth
plt.figure(figsize=(10,5))

plt.plot(z_rough, rough_fscore, marker='o', label="Rough Focus")
plt.plot(z_smooth, smooth_fscore, marker='x', label="Smooth Focus")

plt.xlabel("Z Height (mm)")
plt.ylabel("Focus Score")
plt.title("Focus Score vs Z Height")

plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig("focus_scores3.png")
print("Saved focus_scores.png")



# close windows and turn off light
cv2.destroyAllWindows()
GPIO.cleanup()