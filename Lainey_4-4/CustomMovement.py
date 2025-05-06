import cv2
import numpy as np
import time
import serial
import sys
from focus import run_autofocus_at_current_position
from picamera2 import Picamera2, Preview
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
        print(f"GRBL status response: {out}")

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


# Read the image
image = cv2.imread("NewPlate.png")

# Define the real-world coordinates of the image corners
real_world_coords = np.array([[-3.8, -95.5], [-164, -95.5], [-164, -26], [-4.3, -26]])

# Define the corresponding pixel coordinates in the image
#pixel_coords = np.array([[0, 0], [image.shape[1], 0], [image.shape[1], image.shape[0]], [0, image.shape[0]]])
pixel_coords = np.array([[105, 210], [1216, 210], [1216, 696], [105, 696]])

# areas within camera range
x_min, y_min = 105, 210
x_max, y_max = 1216, 696

# Find the homography matrix to transform pixel coordinates to real-world coordinates
H, _ = cv2.findHomography(pixel_coords, real_world_coords)

# Function to map pixel coordinates to real-world coordinates
def pixel_to_real(x, y, H):
    real_coords = H @ np.array([x, y, 1])
    x1, y1 = real_coords[0] / real_coords[2], real_coords[1] / real_coords[2]
    return x1, y1

# Add instructions to the image
instructions_text = "Drag cursor to create a box around imaging region. Press enter when done."
font = cv2.FONT_HERSHEY_PLAIN
font_scale = 1.5
font_color = (0, 0, 0)
thickness = 2
text_size = cv2.getTextSize(instructions_text, font, font_scale, thickness)[0]
text_x = (image.shape[1] - text_size[0]) // 2  # Center horizontally
text_y = 130
image_text = image.copy()
cv2.putText(image_text, instructions_text, (text_x, text_y), font, font_scale, font_color, thickness)

# Display the image and let the user select an ROI
roi = cv2.selectROI("Select ROI", image_text, fromCenter=False, showCrosshair=True)

# Extract values from ROI (x, y, width, height)
x, y, w, h = roi

# Ensure selection is within the defined bounding box
if x < x_min:
    w = w - (x_min - x)
    x = x_min
if (x + w) > x_max:
    w = x_max - x
if y < y_min:
    h = h - (y_min - y)
    y = y_min
if (y + h) > y_max:
    h = y_max - y
if (x > x_max or y > y_max or (x + w) < x_min or (y + h) < y_min):
    print ("Selection was outside of bounds. Exiting Program.")
    sys.exit()

# Close all windows
cv2.destroyAllWindows()

# Set up serial connection
controller = CNCController(port="/dev/ttyUSB0", baudrate=115200)

# Set up camera
picam2 = Picamera2()

cam_config = picam2.create_preview_configuration(
    main= {"format": "YUV420", "size": (480,360)},#(int(2028/2),int(1520/2))}, #(480,360)},
    # lores = {"format": "XBGR8888","size":(480,360)},# (507,380),(480,360)
    raw={"format": "SRGGB12", "size": (2028,1520)},#(4056,3040)},(2028,1520),(2028,1080)
    display = "main" ,queue=False ,buffer_count=1 #, SRGGB12_CSI2P
)
cam_config["transform"] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(cam_config)


#picam2.start_preview(Preview.DRM)  

def go_to_corner (xCo, yCo):
    # Extract the corner of the ROI
    pixel_x, pixel_y = x, y
    if xCo == 2:
        pixel_x = x + w
    if yCo == 3:
        pixel_y = y + h
    print(f"Selected ROI Pixel Coordinates: ({pixel_x}, {pixel_y})")

    # Map the pixel coordinates of the corner to real-world coordinates
    real_x,real_y = pixel_to_real(pixel_x, pixel_y, H)
    print(f"Mapped Real-World Coordinates: ({real_x:.2f}, {real_y:.2f})")

   
    # Move the robot to the real-world coordinates of the selected ROI's corner
    position = dict()
    position['x_pos'] = real_x
    position['y_pos'] = real_y
    position['z_pos'] = -13
    print(f"Moving to X: {real_x:.2f}, Y: {real_y:.2f}, Z: {-13}")
    controller.move_XYZ(position)
    print("moved")

    #autofocus to find z
    this_well_coords = controller.get_current_position()
    print("I think I am at")
    print(this_well_coords)
    print("now focus z")
    z_height, cap = run_autofocus_at_current_position(controller.ser, this_well_coords, picam2, autofocus_min_max=[-1,1])
    print ("z focused")

def go_to_center ():
    # Extract the center of the ROI
    pixel_x = x + w/2
    pixel_y = y + h/2
    print(f"Selected ROI Pixel Coordinates: ({pixel_x}, {pixel_y})")
   
    # Map the pixel coordinates of the center to real-world coordinates
    real_x,real_y = pixel_to_real(pixel_x, pixel_y, H)
    print(f"Mapped Real-World Coordinates: ({real_x:.2f}, {real_y:.2f})")

    # Move the robot to the real-world coordinates of the selected ROI's corner
    position = dict()
    position['x_pos'] = real_x
    position['y_pos'] = real_y
    position['z_pos'] = -13

    print(f"Moving to X: {real_x:.2f}, Y: {real_y:.2f}, Z: {position['z_pos']}")
    controller.move_XYZ(position)

controller.get_current_position()
# Home Robot
print("Homing robot...")
controller.home_grbl()

print ("corner 1 start")
go_to_corner(0,1)
print ("corner 1 finish")
time.sleep(3)

go_to_corner(2,1)
print ("corner 2")
time.sleep(3)

go_to_corner(2,3)
print ("corner 3")
time.sleep(3)

go_to_corner(0,3)
print ("corner 4")
time.sleep(3)

go_to_center()

# Close the serial connection
controller.close_connection()