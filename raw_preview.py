#!/usr/bin/python3
import time

import cv2, json
import numpy as np

from picamera2 import MappedArray, Picamera2, Preview


def sort_dict(d):
    d_keys = list(d.keys())
    d_keys.sort()
    d = {i: d[i] for i in d_keys}
    return d

picam2 = Picamera2()
cam_config = picam2.create_preview_configuration(
    main= {"format": "XBGR8888", "size": (2028,1520)},
    # lores = {"format": "XBGR8888","size":(2028,1520)},# (507,380),(480,360)
    raw={"format": "SRGGB12", "size": (2028,1520)},#(4056,3040)},(2028,1520),(2028,1080)
    display = "raw",
    # buffer_count=2
)
picam2.configure(cam_config)

picam2.start_preview(Preview.QTGL)


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

colour = (0, 255, 0)
origin = (0, 100)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 3
thickness = 5


def apply_timestamp(request):
    timestamp = time.strftime("%Y-%m-%d %X")
    with MappedArray(request, "main") as m:
        cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)

    with MappedArray(request,"raw") as r:
        r.array.view(np.uint16)


picam2.pre_callback = apply_timestamp

picam2.start()
time.sleep(10)

