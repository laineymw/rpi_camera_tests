# import libraries
from utils import *
import os, time, cv2, serial, csv
import numpy as np
import get_settings
import camera_control
# import matplotlib.pyplot as plt
# from tkinter import Tk
# from movement import simple_stream

def send_command(ser, command, verbose = True):
    try:
        # Send the command to the CNC
        if verbose:
            ser.write(f"{command}\n".encode())
        print(f"Sent: {command}")

        time.sleep(0.1)

        # Wait for an "OK" response from the CNC
        while True:
            response = ser.readline().decode().strip()
            if response:
                print(f"Response: {response}")
                if response.lower() == "ok":  # CNC signals completion
                    print("Command sent.")
                    break
                elif "error" in response.lower():
                    print(f"Error received: {response}")
                    break
    except Exception as e:
        print(f"Error sending command: {e}")

def send_command_v2(ser,command, verbose = True):
    try:
        # Send the command to the CNC
        ser.write(f"{command}\n".encode())
        if verbose:
            print(f"Sent: {command}")

        time.sleep(0.1)

        # make sure that its actually done moving 
        if ('$X' not in command) and ('$$' not in command) and ('?' not in command):
            idle_counter = 0
            time.sleep(0.025)
            while True:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.025)
                command = str.encode("?"+ "\n")
                ser.write(command)
                time.sleep(0.025)
                grbl_out = ser.readline().decode().strip()
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
    except Exception as e:
        print(f"Error sending command: {e}")

def move_to(ser, x, y, z, verbose = True):
    send_command_v2(ser, f'G0 X{x} Y{y} Z{z}', verbose)

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


# finds the z position that gets the best focus
def run_autofocus_at_current_position(ser, starting_location, cam,
        autofocus_min_max=[1, -1], autofocus_delta_z=0.10, cap=None, verbose = True):

    print("FOCUSING CAMERA")
    autofocus_steps = int(abs(np.diff(autofocus_min_max) / autofocus_delta_z)) + 1
    z_limit = [10, -94]
    offset = 25  # this is for the autofocus algorithm, how many pixels apart is the focus to be measured
    thresh = 5  # same as above but now ignores all the values under thresh

    # find the z locations for the loop to step through
    z_positions_start = np.linspace(
        starting_location['z_pos'] + autofocus_min_max[0],
        starting_location['z_pos'] + autofocus_min_max[1],
        num=autofocus_steps
    )
    z_positions = []
    images = []
    uncalib_fscore = []
    buffer_num = 5 # this used to be 10

    for counter, z_pos in enumerate(z_positions_start):
        this_location = starting_location.copy()
        this_location['z_pos'] = z_pos
        if z_limit[0] > z_pos > z_limit[1]:
            z_positions.append(z_pos)
            if verbose:
                print("this location")
                print(this_location)
            move_to(ser, this_location['x_pos'], this_location['y_pos'], this_location['z_pos'], verbose)
            for i in range(buffer_num):
                array_to_process = cam.capture_array("raw")#,"lores"]) #"main","lores","raw"
                array_to_process = process_raw(array_to_process, G= True, rgb_or_bgr=False)#, G = True) # RGB = True, 
                if i == buffer_num-1:
                    test = np.float32(array_to_process)/(2**16)
                    cv2.imwrite('focus_{counter}_Image.jpg', test)
            #frame = frame[:,:,2]
            images.append(array_to_process)
            temp = sq_grad(array_to_process, thresh=thresh, offset=offset)
            uncalib_fscore.append(np.sum(temp))

            if counter == 0:
                maxVal = np.max(array_to_process) 
            im_to_show = array_to_process.astype(np.float32) / maxVal
            im_to_show = np.clip(im_to_show, 0.0, 1.0)
            im_to_show = (im_to_show * 255).astype(np.uint8)
            camera_control.imshow_resize(frame_name="stream", frame=im_to_show,move_to = [1920-960,100],
                                         resize_size = [960,720])

   
    # output_dir = "autofocus_images"
    # if not os.path.exists(output_dir):
    #     os.makedirs(output_dir)

    # for i, img in enumerate(images):
    #     img_path = os.path.join(output_dir, f"image_{i}.png")
    #     cv2.imwrite(img_path, img)

    del images # this deletes the stack of images

    assumed_focus_idx = np.argmax(uncalib_fscore)
    z_pos = z_positions[assumed_focus_idx]  # for the final output
    this_location = starting_location.copy()
    this_location['z_pos'] = z_positions[assumed_focus_idx] + 0.05
    move_to(ser, this_location['x_pos'], this_location['y_pos'], this_location['z_pos'], verbose)
    for i in range(buffer_num):
        array_to_process = cam.capture_array("raw")#,"lores"]) #"main","lores","raw"
        array_to_process = process_raw(array_to_process, G= True, rgb_or_bgr=False)#, G = True) # RGB = True, 
        # if i == buffer_num:
        #     test = np.float32(array_to_process)/(2**16)
        #     cv2.imwrite('focusImage.jpg', test) 
    camera_control.imshow_resize(frame_name="stream", frame=array_to_process,move_to = [1920-960,100],
                                 resize_size = [960,720])
    if verbose:
        print('CAMERA FOCUSED')
    return z_pos, cap, uncalib_fscore, z_positions#cam


# function used within autofocus
def sq_grad(img, thresh=50, offset=10):
    shift = int(0 - offset)
    offset = int(offset)

    img1 = img[:, 0:shift].astype(np.float32)
    img2 = img[:, offset:].astype(np.float32)

    diff = np.abs(img2 - img1)
    mask = diff > thresh
    squared_gradient = diff * diff * mask

    return squared_gradient


# set up controller class for movement
class CNCController:
    def __init__(self, port, baudrate):
        import re
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)

    def send_command(self, command):
        self.ser.reset_input_buffer()  # flush the input and the output
        self.ser.reset_output_buffer()
        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        return self.ser.readline().decode().strip()

    def move_XYZ(self, position):
        command = f'G1 X{position["x_pos"]} Y{position["y_pos"]} Z{position["z_pos"]} F2500'
        return self.send_command(command)


# reading CSV file of well positions
def read_positions_from_csv(filename):
    positions = []
    with open(filename, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # skipping the header
        for row in reader:
            x, y, z = map(float, row[:3])  # Extract first three columns as positions
            name = row[3]
            positions.append((x, y, z, name))  # Append to positions list
    return positions