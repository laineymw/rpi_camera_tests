import os,time,glob
import numpy as np
from pprint import pprint
import matplotlib.pyplot as plt

from picamera2 import Picamera2, Preview

os.makedirs('images',exist_ok=True)
picam2 = Picamera2()

capture_config = picam2.create_still_configuration(
    main= {"format": "XBGR8888", "size": (2028,1520)},
    lores = {"format": "XBGR8888","size":(640,480)}, 
    raw={'format': 'SRGGB12_CSI2P', "size": (4056,3040)},
    display = None)#"lores")
picam2.configure(capture_config)

picam2.start()
# time.sleep(0.5)

arrays, metadata = picam2.switch_mode_and_capture_buffers(capture_config, ["raw","main","lores"],delay = 4)

raw_shape = arrays[0].shape

width = picam2.camera_configuration()['raw']['size'][0]
height = picam2.camera_configuration()['raw']['size'][1]

a = arrays[0]
# a2 = a[:,:-40]

R = a[0::4]

files = glob.glob(os.path.join("images","*"))
for f in files:
    os.remove(f)

picam2.helpers.save_dng(arrays[0], metadata, capture_config["raw"], os.path.join("images","full.dng"))
picam2.helpers.save(picam2.helpers.make_image(arrays[1],capture_config["main"]), metadata, os.path.join("images","compressed.png"))
picam2.helpers.save(picam2.helpers.make_image(arrays[2],capture_config["lores"]), metadata, os.path.join("images","compressed_lowres.jpg"))


print('eof')