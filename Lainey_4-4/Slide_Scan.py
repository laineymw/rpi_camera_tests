import time, serial, libcamera, cv2, datetime, copy, os
from picamera2 import Picamera2, Preview
import RPi.GPIO as GPIO
import numpy as np
from pathlib import Path
from math import ceil
from focus import run_autofocus_at_current_position
import camera_control
from skimage.filters.rank import entropy
from skimage.morphology import disk
from datetime import datetime

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

def calculateCoOrds (xOrigin, yOrigin, row, col, nRows, nCols, RowHeight, ColumnWidth):
    Coordinates = []
    if nRows % 2 == 0:
        y = yOrigin - (RowHeight * (abs(row)-0.5)*(row/abs(row)))
    else:
        y = yOrigin + (row * RowHeight)
   
    if nCols % 2 == 0:
        x = xOrigin - (ColumnWidth * (abs(col)-0.5)*(col/abs(col)))
    else:
        x = xOrigin + (col * ColumnWidth)
    Coordinates.append(x)
    Coordinates.append(y)

    return Coordinates

def getRowsOrCols (Amount):
    RowsOrCols = []
    if Amount % 2 == 0:
        for i in range(-Amount // 2, 0):
            RowsOrCols.append(i)
        for i in range (1, (Amount // 2) + 1):
            RowsOrCols.append(i)

    else:
        for i in range (0, Amount):
            j = i - (Amount - 1) / 2
            RowsOrCols.append(j)
    return RowsOrCols

def snakeCoordinates (xOrigin, yOrigin, ScanWidth_mm, ScanHeight_mm, Overlap,
                    ImageWidthPix = 1024, ImageHeightPix = 760, PixToMm = 2.55/286):

    ImageWidth_mm = PixToMm * ImageWidthPix
    ImageHeight_mm = PixToMm * ImageHeightPix
    FinalWidth = ImageWidth_mm * (1 - (2 * Overlap))
    FinalHeight = ImageHeight_mm * (1 - (2 * Overlap))

    nColumns = ceil(ScanWidth_mm / FinalWidth)
    nRows = ceil(ScanHeight_mm / FinalHeight)

    Rows = []
    Columns = []
    Rows = getRowsOrCols(nRows)
    Columns = getRowsOrCols(nColumns)

    RowHeight = ScanHeight_mm / nRows
    ColumnWidth = ScanWidth_mm / nColumns

    Coordinates = []

    counter = 0
    for i in Rows:
        if counter % 2 == 0:
            for j in Columns:
                CoordinatePair = calculateCoOrds(xOrigin, yOrigin, i, j, nRows, nColumns, RowHeight, ColumnWidth)
                Coordinates.append(CoordinatePair)
        else:
            for j in reversed(Columns):
                CoordinatePair = calculateCoOrds(xOrigin, yOrigin, i, j, nRows, nColumns, RowHeight, ColumnWidth)
                Coordinates.append(CoordinatePair)
        counter += 1

    return Coordinates

def processHistogram (array):
    temp_array_uint8 = ((array.astype(np.float32)/array.max())*255).astype(np.uint8)

    # Gaussian smoothing
    gaussian_array = cv2.GaussianBlur(temp_array_uint8, (7, 7), 5)

    # Entropy filter
    entropy_array = entropy(gaussian_array, disk(10))

    uint8_array = (entropy_array * (255 / entropy_array.max())).astype(np.uint8)

    # Threshold
    threshold_array = copy.deepcopy(uint8_array)
    threshold = threshold_array.mean() + 4 * threshold_array.std()
    threshold_array[threshold_array < threshold] = 0

    return threshold_array
    

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
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
folder_path = documents / f"Run_{timestamp}"
os.makedirs(folder_path, exist_ok=True)

# home
controller.home_grbl()

# set scan variables
xOrigins = [-25.5, -24.5, -24.5, -82.0, -81.7, -81.7, -138.5, -135.0, -138.0]
yOrigins = [-95.0, -69.5, -41.0, -93.5, -69.5, -44.5, -92.0, -68.0, -42.0]
ScanWidth_mm = 14.5
ScanHeight_mm = 14.5
Overlap = 0.1
position = dict()
maxPosition = dict()
positionInfo = []
brightness_array = []
counter = 0

# loop through all slides
for origin_index, (xOrigin, yOrigin) in enumerate(zip(xOrigins, yOrigins)):
    # for saving all images
    slide_folder = folder_path / f"Slide_{origin_index}"
    os.makedirs(slide_folder, exist_ok=True)

    sampleCoordinates = snakeCoordinates(xOrigin, yOrigin, ScanWidth_mm, ScanHeight_mm, Overlap)

    positionInfo = []
    maxBrightness = -np.inf
    maxIndex = None

    # loop through all positions
    for i,val in enumerate(sampleCoordinates):

        # go to position and focus
        x, y = val
        position['x_pos'] = x
        position['y_pos'] = y
        position['z_pos'] = -6.9
        print(f"moving to position {i}")
        controller.move_XYZ(position)
        this_well_coords = controller.get_current_position()
        z_height, cap = run_autofocus_at_current_position(
            controller.ser, this_well_coords, picam2,
            autofocus_min_max=[-2, 2], autofocus_delta_z= (1/3),
            verbose = False
        )
        
        # clear buffer
        for buffer in range (5):
            array_to_process = picam2.capture_array("raw")

        # capture image as uint8
        array_to_process = picam2.capture_array("raw")
        processed_array = process_raw(array_to_process, G = True )
        temp_array = copy.deepcopy(processed_array)
        temp_array_uint8 = ((temp_array.astype(np.float32)/((2**16)-1))*255).astype(np.uint8)

        # for saving all images
        focus_filename = slide_folder / f"focus_{i:04d}.png"
        cv2.imwrite(str(focus_filename), temp_array_uint8)

        # process image and calculate brightness
        segmented_array = processHistogram(temp_array_uint8)
        brightness = np.sum(segmented_array.astype(np.float32))
        camera_control.imshow_resize(frame_name="stream", frame=segmented_array, move_to = [1920-960,100], resize_size = [960,720])
        positionInfo.append([i, x, y, z_height, brightness])
        
        # calculate max brightness
        if i == 0:
            maxBrightness = brightness
            maxIndex = i
        
        if brightness > maxBrightness:
            maxBrightness = brightness
            maxIndex = i

        print(np.array(segmented_array))

    # move to worms and focus
    maxPosition['x_pos'] = positionInfo[maxIndex][1]
    maxPosition['y_pos'] = positionInfo[maxIndex][2]
    maxPosition['z_pos'] = positionInfo[maxIndex][3]
    print("moving to worms")
    controller.move_XYZ(maxPosition)
    this_well_coords = controller.get_current_position()
    z_height, cap = run_autofocus_at_current_position(
            controller.ser, this_well_coords, picam2, autofocus_min_max=[-2, 2], 
            autofocus_delta_z= (1/3), verbose = False
        )
    
    # clear buffer
    for buffer in range (5):
        array_to_process = picam2.capture_array("raw")

    # capture image
    array_to_process = picam2.capture_array("raw")
    array_to_process = process_raw(array_to_process, RGB=True, rgb_or_bgr=False)
    cv2.imwrite("test.png", array_to_process)
    #normalized_image = (array_to_process.astype(np.float32) / array_to_process.max() * 65535).astype(np.uint16)
    #normalized_image = array_to_process.astype(np.float32) / np.max(array_to_process) # ONLY to make it standard for exports

    # name the file with position index and timestamp 
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = folder_path / f"pos_{counter}_{timestamp}.png" 

    # Save image
    cv2.imwrite(str(filename), array_to_process)
    print(f"Image saved to: {filename}")

    # show image
    cv2.namedWindow("Captured Image", cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty("Captured Image",cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)
    cv2.imshow("Captured Image", array_to_process)

    counter += 1
    time.sleep(1)
    cv2.destroyWindow("Captured Image")

# close windows and turn off light
cv2.destroyAllWindows()
GPIO.cleanup()