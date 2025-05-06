import cv2
import numpy as np
import time
import serial
from picamera2 import Picamera2, Preview


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


# Set up serial connection
controller = CNCController(port="/dev/ttyUSB0", baudrate=115200)

controller.get_current_position()
# Home Robot
print("Homing robot...")
controller.home_grbl()
controller.get_current_position()

position = dict()
position['x_pos'] = -4.3
position['y_pos'] = -26
position['z_pos'] = -13

print ("moving to position")
controller.move_XYZ(position)
print("move complete")
time.sleep(3)
controller.get_current_position()

# Close the serial connection
controller.close_connection()