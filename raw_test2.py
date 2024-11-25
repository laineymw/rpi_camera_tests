# Capture multiple representations of a captured frame.

import time
import matplotlib.pyplot as plt
import numpy as np

from picamera2 import Picamera2, Preview

def s(tmp):
    plt.imshow(tmp)
    plt.show(block=True)

picam2 = Picamera2()
# picam2.start_preview(Preview.QTGL)

# preview_config = picam2.create_preview_configuration(raw={"size": (4056,3040)},main={"size": (4056,3040)})
capture_config = picam2.create_still_configuration(raw={"size": (4056,3040)},main={"size": (4056,3040)})
# picam2.configure(preview_config)

picam2.start()
# time.sleep(2)

buffers, metadata = picam2.switch_mode_and_capture_buffers(capture_config, ["main","raw"],delay=4)

arr = picam2.helpers.make_array(buffers[0], capture_config["main"])
image = picam2.helpers.make_image(buffers[0], capture_config["main"])
arr2 = picam2.helpers.make_array(buffers[1], capture_config["raw"])

a = picam2.helpers.decompress(arr2) # i dont know what these do but the internet says they good
b = arr2 >> 6

image2 = picam2.helpers.make_image(buffers[1], capture_config["raw"])

print('eof')
