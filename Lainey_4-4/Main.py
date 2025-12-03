#!/usr/bin/env python3
def show_loading_screen():
    import tkinter as tk
    from tkinter import ttk

    loading = tk.Tk()
    loading.title("Loading...")

    # defualt is 0
    side_pixels_buffer = 100

    # Get screen dimensions
    w = loading.winfo_screenwidth() - side_pixels_buffer*2
    h = loading.winfo_screenheight() - side_pixels_buffer*2

    # Make it fullscreen
    loading.geometry(f"{w}x{h}+{side_pixels_buffer}+{side_pixels_buffer}")
    loading.configure(bg="black")

    # Remove window decorations (optional)
    loading.overrideredirect(True)

    label = ttk.Label(
        loading,
        text="Starting up...\nPlease wait",
        font=("Segoe UI", 60, "bold"),
        foreground="white",
        background="black",
        anchor="center",
        justify="center"
    )
    label.pack(expand=True)

    # Auto-close after 4.5 sec (adjust as needed)
    loading.after(2000, loading.destroy)
    loading.mainloop()

show_loading_screen()

import time, serial, cv2, libcamera, os
import numpy as np
from picamera2 import Picamera2, Preview
from focus import run_autofocus_at_current_position
import RPi.GPIO as GPIO
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGridLayout, QLabel,
    QPushButton, QCheckBox, QMainWindow
)
from PySide6.QtCore import Qt
import sys

from pathlib import Path

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

def get_user_selected_position():
    import tkinter as tk
    from tkinter import ttk
    import ttkbootstrap as tb
    from pathlib import Path
    import os

    POSITIONS = {
        "Left slide- top": {'x_pos': -25.5, 'y_pos': -95, 'z_pos': -6.9},
        "Left slide- middle": {'x_pos': -24.5, 'y_pos': -69.5, 'z_pos': -6.9},
        "Left slide- bottom": {'x_pos': -25.5, 'y_pos': -41, 'z_pos': -6.9},

        "Center slide- top": {'x_pos': -82.0, 'y_pos': -93.5, 'z_pos': -5.75},
        "Center slide- middle": {'x_pos': -81.7, 'y_pos': -69.5, 'z_pos': -6.9},
        "Center slide- bottom": {'x_pos': -81.7, 'y_pos': -44.5, 'z_pos': -5.9},

        "Right slide- top": {'x_pos': -138.5, 'y_pos': -92, 'z_pos': -5.9},
        "Right slide- middle": {'x_pos': -135.0, 'y_pos': -68.0, 'z_pos': -5.9},
        "Right slide- bottom": {'x_pos': -138.0, 'y_pos': -42, 'z_pos': -5.5}
    }

    selected_positions = []

    # Dark mode theme
    root = tb.Window(themename="superhero")
    root.title("Select Slide Positions")

    # Default offset from screen edges
    side_pixels_buffer = 100

    # Get screen dimensions
    w = root.winfo_screenwidth() - side_pixels_buffer * 2
    h = root.winfo_screenheight() - side_pixels_buffer * 2

    # Make it fullscreen
    root.geometry(f"{w}x{h}+{side_pixels_buffer}+{side_pixels_buffer}")

    # ---------- Dynamic scaling ----------
    title_font_size = int(h * 0.08)
    button_font_size = int(h * 0.07)
    check_font_size = int(h * 0.04)

    pad_y = int(h * 0.002)
    pad_x = int(w * 0.002)

    # Layout configuration
    root.grid_columnconfigure(0, weight=1)
    root.grid_columnconfigure(1, weight=0)
    root.grid_columnconfigure(2, weight=1)

    # Instructions
    instruction_font_size = int(title_font_size * 0.65)
    instruction = ttk.Label(
        root,
        text="Select one or more slide positions, then click Done.",
        anchor="center",
        justify="center",
        font=("Segoe UI", instruction_font_size, "bold")
    )
    instruction.grid(row=0, column=0, columnspan=3, pady=(pad_y, pad_y))

    var_dict = {}

    # Toggle Select All / Clear All
    def toggle_all():
        all_selected = all(var.get() == 1 for var in var_dict.values())
        for var in var_dict.values():
            var.set(0 if all_selected else 1)
        select_all_btn.config(text="Select All" if all_selected else "Clear All")

    select_all_btn = tk.Button(
        root, text="Select All", command=toggle_all,
        font=("Segoe UI", 20, "bold")
    )
    select_all_btn.grid(
        row=1, column=0, columnspan=3,
        pady=(0, pad_y), ipadx=20, ipady=20,
        sticky="ew"
    )

    # Frame for toggle grid
    toggles_frame = ttk.Frame(root)
    toggles_frame.grid(row=2, column=1, pady=(0, pad_y))

    for c in range(3):
        toggles_frame.grid_columnconfigure(c, weight=1)

    labels = [
        ["Left slide- top", "Center slide- top", "Right slide- top"],
        ["Left slide- middle", "Center slide- middle", "Right slide- middle"],
        ["Left slide- bottom", "Center slide- bottom", "Right slide- bottom"]
    ]

    # Create large checkboxes
    for r, row in enumerate(labels):
        for c, label in enumerate(row):
            var = tk.IntVar()
            chk = tk.Checkbutton(
                toggles_frame,
                text=label,
                variable=var,
                font=("Segoe UI", check_font_size, "bold"),
                anchor="w",
                padx=pad_x // 2,
                pady=pad_y // 2
            )
            chk.grid(row=r, column=c, padx=pad_x, pady=pad_y, sticky="nsew")
            var_dict[label] = var

    def on_done():
        nonlocal selected_positions
        selected_positions = [POSITIONS[label] for label, v in var_dict.items() if v.get() == 1]
        if selected_positions:
            root.quit()
        else:
            import tkinter.messagebox as msg
            msg.showwarning("No Selection", "Please select at least one position.")

    def on_quit():
        nonlocal selected_positions
        selected_positions = None
        root.quit()

    def delete_images():
        desktop = Path.home() / "Desktop"
        deleted_count = 0
        for file in desktop.glob("*.png"):
            try:
                os.remove(file)
                deleted_count += 1
            except Exception as e:
                print(f"Could not delete {file}: {e}")
        print(f"Deleted {deleted_count} image(s) from Desktop.")

    # --- Action buttons layout ---

    # DONE button (top of action section)
    done_btn = tk.Button(root, text="Done", command=on_done,
                         font=("Segoe UI", 20, "bold"))
    done_btn.grid(row=3, column=0, columnspan=3,
                  pady=(pad_y, pad_y), ipadx=20, ipady=25,
                  sticky="ew")

    # Frame for Quit + Clear Images buttons side-by-side
    bottom_buttons_frame = ttk.Frame(root)
    bottom_buttons_frame.grid(row=4, column=0, columnspan=3, pady=(pad_y, pad_y), sticky="ew")

    bottom_buttons_frame.grid_columnconfigure(0, weight=1)
    bottom_buttons_frame.grid_columnconfigure(1, weight=1)

    quit_btn = tk.Button(bottom_buttons_frame, text="Quit", command=on_quit,
                         font=("Segoe UI", 20, "bold"))
    quit_btn.grid(row=0, column=0, padx=(pad_x, pad_x//2), ipadx=20, ipady=25, sticky="ew")

    delete_btn = tk.Button(bottom_buttons_frame, text="Clear Images", command=delete_images,
                           font=("Segoe UI", 20, "bold"))
    delete_btn.grid(row=0, column=1, padx=(pad_x//2, pad_x), ipadx=20, ipady=25, sticky="ew")

    # --- Main loop ---
    root.mainloop()
    try:
        root.destroy()
    except Exception:
        print('Probably an error during cleanup')

    return selected_positions
    
print('setting up controller')
# set up serial connection
controller = CNCController(port="/dev/ttyUSB0", baudrate=115200)

print('setting up camera')
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

imaging_config = picam2.create_preview_configuration(
    main= {"format": "YUV420", "size": (480,360)},
    raw={"format": "SRGGB12", "size": (4056,3040)},
    display = "main"  ,buffer_count=2 
)
imaging_config["transform"] = libcamera.Transform(hflip=1, vflip=1)

running = True

# set up desktop path for saving
desktop = Path.home() / "Desktop"
documents = Path.home() / "Documents"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
folder_path = documents / f"Run_{timestamp}"
os.makedirs(folder_path, exist_ok=True)

while running:
    print('getting user selection')
    # get user-selected position from GUI
    chosen_position = get_user_selected_position()

    if chosen_position is None:
        running = False
        break

    # turn light on
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(26, GPIO.OUT)
    GPIO.output(26, GPIO.HIGH)

    preview_width = int(1920/2)
    preview_height = int(1920/2) #640 #int(1080/2)
    preview = picam2.start_preview(Preview.QTGL,x=1920-preview_width,y=1, width = preview_width, height = preview_height)
    picam2.set_controls({'AnalogueGain':16})
    picam2.start()

    # home robot
    print("Homing robot...")
    controller.home_grbl()

    print("Moving to selected positions and capturing images...")
    for idx, pos in enumerate(chosen_position): 

        # set the resolution low for focusing
        if idx != 0:
            picam2.stop()
            picam2.configure(cam_config)
            picam2.start()

        if idx == 0:
            x = np.arange(1024)
            y = np.arange(760)
            xx,yy = np.meshgrid(x,y)

        # move CNC
        controller.move_XYZ(pos)
        print(f"Arrived at {pos}")

        # rough focus
        this_well_coords = controller.get_current_position()
        z_height, cap = run_autofocus_at_current_position(
            controller.ser, this_well_coords, picam2,
            autofocus_min_max=[-2, 2], autofocus_delta_z= (1/3)
        )
        this_well_coords = controller.get_current_position()
        
        # # center camera around worms
        # temp_img = picam2.capture_array("raw")
        # temp_img = process_raw(temp_img,G=True)
        # temp_img[temp_img<5000] = 0
        # temp_img_sum = temp_img.sum()
        # x_cms = (xx*temp_img).sum()/temp_img_sum
        # y_cms = (yy*temp_img).sum()/temp_img_sum
        # adjusted_coords = controller.get_current_position()
        # adjusted_coords['y_pos'] = adjusted_coords['y_pos'] - list(((np.asarray(temp_img.shape[0])/2)-np.asarray([y_cms]))/114)[0]
        # adjusted_coords['x_pos'] = adjusted_coords['x_pos'] + list(((np.asarray(temp_img.shape[1])/2)-np.asarray([x_cms]))/114)[0]
        # controller.move_XYZ(adjusted_coords)
        print("Z focused 1/2")

        # fine focus
        this_well_coords = controller.get_current_position()
        z_height, cap = run_autofocus_at_current_position(
            controller.ser, this_well_coords, picam2,
            autofocus_min_max=[-0.3, 0.3], autofocus_delta_z=0.1
        )
        print("Z focused 2/2")
        time.sleep(1)

        '''
        # set resolution high for imaging
        print('stopping camera')
        picam2.stop()
        picam2.configure(imaging_config)
        print('starting camera')
        picam2.start()
        '''
        
        # get rid of any delay
        buffer_num = 2
        for i in range(buffer_num):
            array_to_process = picam2.capture_array("raw")

        # capture image
        array_to_process = picam2.capture_array("raw")
        array_to_process = process_raw(array_to_process, RGB=True, rgb_or_bgr=False)
        cv2.imwrite("test.png", array_to_process)
        normalized_image = array_to_process.astype(np.float32) / 30000# np.max(array_to_process) # ONLY to make it standard for exports

        # normalize exported image
        export_image = np.clip(normalized_image*255,a_min= 0,a_max = 255).astype(np.uint8)

        # name the file with position index and timestamp 
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = desktop / f"pos:{idx+1}_{timestamp}.png"
        filename2 = documents / f"pos:{idx+1}_{timestamp}.png"

        # Save image
        cv2.imwrite(str(filename), export_image)
        cv2.imwrite(str(filename2), export_image)
        print(f"Image saved to: {filename}")

        # show image
        cv2.namedWindow("Captured Image", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Captured Image",cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)
        cv2.imshow("Captured Image", normalized_image)
        time.sleep(1)
        cv2.destroyWindow("Captured Image")


    # close windows and turn off light
    cv2.destroyAllWindows()
    GPIO.cleanup()