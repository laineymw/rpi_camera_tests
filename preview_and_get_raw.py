from concurrent.futures import ThreadPoolExecutor
import os, time, datetime, subprocess
import glob
import json
import piexif
from PIL import Image
import numpy as np
from picamera2 import Picamera2, Preview
# from pprint import pprint
import matplotlib.pyplot as plt
import cv2

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

def sort_dict(d):
    d_keys = list(d.keys())
    d_keys.sort()
    d = {i: d[i] for i in d_keys}
    return d

def s(tmp, bgr=False,f=False):
    if f:#(fig is not None) and (ax is not None):
        global fig, ax
        ax.clear()  # Clear only the axes instead of recreating the figure
        ax.imshow(tmp)  # Use grayscale if applicable
        # plt.draw()
        # fig.canvas.draw()
        # plt.pause(0.000001)
        fig.canvas.draw_idle()  # Refresh the figure without blocking
        fig.canvas.flush_events()  # Process GUI events
        # plt.pause(0.0001)
    else:
        # global fig, ax
        if bgr:
            tmp = tmp[:, :, ::-1]  # Convert BGR to RGB
        plt.imshow(tmp)
        plt.pause(0.000001)

if __name__ == "__main__":

    monitor_size = subprocess.Popen('xrandr | grep "\*" | cut -d" " -f4', shell = True, stdout = subprocess.PIPE).communicate()[0]
    if monitor_size:
        monitor_size = monitor_size.decode('UTF-8')
        monitor_size = monitor_size.split('x')
        monitor_size[1] = monitor_size[1][:-1]
        monitor_size[0], monitor_size[1] = int(monitor_size[0]), int(monitor_size[1])

    output_path = os.path.join(os.path.dirname(os.path.realpath(__name__)),'images')
    os.makedirs(output_path,exist_ok=True)

    use_preview = True
    use_default_preview_size = True

    picam2 = Picamera2()

    cam_config = picam2.create_preview_configuration(
        main= {"format": "YUV420", "size": (480,360)},#(int(2028/2),int(1520/2))}, #(480,360)},
        # lores = {"format": "XBGR8888","size":(480,360)},# (507,380),(480,360)
        raw={"format": "SRGGB12", "size": (2028,1520)},#(4056,3040)},(2028,1520),(2028,1080)
        display = "main" ,queue=False ,buffer_count=4 #, SRGGB12_CSI2P
    )
    picam2.configure(cam_config)

    if use_preview:
        if use_default_preview_size:
            image_WH = [600,450]
            if monitor_size:
                picam2.start_preview(Preview.QTGL,
                    x=monitor_size[0]-int(image_WH[0]),
                    y=1, 
                    width = int(image_WH[0]),
                    height = int(image_WH[1]))
            else:
                picam2.start_preview(Preview.QTGL,x=500,y=1, width = 640, height = 480)
        else:
            viewer_multiplier = 2.5
            image_WH = [int(viewer_multiplier*cam_config['lores']['size'][0]),
                        int(viewer_multiplier*cam_config['lores']['size'][1])]
            if monitor_size:
                picam2.start_preview(Preview.QTGL,
                    x=monitor_size[0]-int(image_WH[0]),
                    y=1, 
                    width = int(image_WH[0]),
                    height = int(image_WH[1]))
            else:
                picam2.start_preview(Preview.QTGL,x=500,y=1, width = 640, height = 480)

    main_camera_stream_config = cam_config['main']

    # open the default image metadata and read in the settings as a sorted dict
    with open("/home/r/rpi_camera_tests/camera_settings.txt") as f:
        default_image_settings = f.read()
    default_image_settings = json.loads(default_image_settings)
    default_image_settings = sort_dict(default_image_settings)

    # apply the default settings to the current camera
    for key in default_image_settings:
        try:
            picam2.set_controls({key:default_image_settings[key]})
            print(key,default_image_settings[key])
        except:
            print('FAIL to set camera setting')
            print(key,default_image_settings[key])

    exp_time = 1/60
    exp_time_us = int(round(exp_time * 1000000))
    picam2.set_controls({"ExposureTime": exp_time_us}) # overwrite the exposre for testing
            
    picam2.start()
    time.sleep(0.5)
    picam2.title_fields = ["ExposureTime","AnalogueGain","DigitalGain"] # v"ExposureTime","AnalogueGain","DigitalGain",
    time.sleep(0.5)

    print('capturing data')

    # Variables for FPS calculation
    start_time = time.time()
    frame_count = 0
    fps_update_interval = 3  # Seconds
    loop_counter = 0
    loop_counter_max = 5
    display_raw_data = False
    display_adjusted_color = True # this is only for displaying images doesnt affect raw img
    center_crop = False

    stacked_arrays = []

    # create the window and move it to the bottom right
    
    if center_crop:
        window_size = (360,360,3) #(760,760,3) #
        test_array = np.zeros(window_size,dtype = np.uint8)
    else:
        window_size = (360,480,3)#(760, 1024, 3) #
        test_array = np.zeros(window_size,dtype = np.uint8)
    window_name = "filtered_image"
    if display_raw_data:
        cv2.imshow(window_name,test_array)
        cv2.namedWindow(window_name,cv2.WINDOW_AUTOSIZE) # cv2.WINDOW_NORMAL OR cv2.WINDOW_AUTOSIZE
        cv2.moveWindow(window_name,10,monitor_size[1]-window_size[0]-150)

    # set up running average parameters
    alpha = 0.5
    running_avg = None
    # scaler = 1/16384 # 2**14
    scaler = 1/(2**16)

    while True:

        array_to_process = picam2.capture_array("raw")#,"lores"]) #"main","lores","raw"
        # camera_metadata = main_camera_stream_config
        # metadata["ISO"] = round(100*metadata["AnalogueGain"])
        array_to_process = process_raw(array_to_process, RGB= True, rgb_or_bgr=False)#, G = True) # RGB = True, 
        
        if display_raw_data:
            # convert to uint8 for display ease
            display_img = (array_to_process >> 8).astype(np.uint8)

            if display_adjusted_color and (len(display_img.shape) > 2):
                # convert back to uint16 for overflow 
                display_img = display_img.astype(np.uint16)
                # assume using BGR
                display_img[...,0] = display_img[...,0]*default_image_settings['ColourGains'][1]
                display_img[...,2] = display_img[...,2]*default_image_settings['ColourGains'][0]
                display_img = np.clip(display_img,a_min=0,a_max=255).astype(np.uint8)

            img_shape = display_img.shape
            # check if the display image fits in the display window
            if img_shape != window_size and img_shape != window_size[0:2]:
                display_img = cv2.resize(display_img,(window_size[1],window_size[0]))

        if center_crop:
            if not display_raw_data:
                display_img = np.float32((array_to_process))
            img_shape = display_img.shape
            center = [img_shape[0]/2,img_shape[1]/2]
            small_side = min(img_shape[0:2])
            y1,y2 = int(center[0]-small_side/2), int(center[0]+small_side/2)
            x1,x2 = int(center[1]-small_side/2), int(center[1]+small_side/2)
            display_img = display_img[y1:y2,x1:x2]            
            
        if display_raw_data:
            cv2.imshow(window_name,display_img) # 
            cv2.waitKey(1)

        # Increment frame count
        frame_count += 1

        # Calculate and print FPS every 5 seconds
        elapsed_time = time.time() - start_time
        if elapsed_time >= fps_update_interval:

            fps = frame_count / elapsed_time
            print(f"FPS: {fps:.2f} --- LOOP: {loop_counter:.0f}")

            start_time = time.time()
            frame_count = 0






