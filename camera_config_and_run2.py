from concurrent.futures import ThreadPoolExecutor
import os, time
import glob
import json
import piexif
from PIL import Image, PngImagePlugin
import numpy as np
from picamera2 import Picamera2, Preview
from pprint import pprint
import matplotlib.pyplot as plt

def save_image_with_metadata(array, filepath, metadata=None, capture_config=None, format="PNG", quality=95):
    if isinstance(array, np.ndarray):
        if array.ndim == 3 and array.shape[2] > 3:
            array = array[:, :, 0:3]

    if not isinstance(array, np.ndarray) or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("Input must be an M, N, 3 NumPy array in RGB format.")

    # Try to convert to BGR
    try:
        color_format = capture_config[0][capture_config[1]]['format']
        if 'RGB' in color_format.upper():
            array = array[:, :, ::-1]
    except Exception:
        pass  # Colorspace detection failed

    # Convert the array to a PIL Image
    image = Image.fromarray(array, 'RGB')

    if format.upper() == "PNG":
        info = PngImagePlugin.PngInfo()
        if metadata:
            for key, value in metadata.items():
                info.add_text(key, str(value))
        image.save(filepath, format="PNG", pnginfo=info)
    elif format.upper() in {"JPEG", "JPG"}:
        if metadata:
            exif_dict = {"Exif": {}, "0th": {}, "1st": {}}
            exif_dict["Exif"][piexif.ExifIFD.ExposureTime] = (metadata.get("ExposureTime", 1), 1)
            exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings] = metadata.get("ISO", 100)
            exif_dict["Exif"][piexif.ExifIFD.ImageUniqueID] = str(metadata.get("SensorTimestamp", ""))
            exif_bytes = piexif.dump(exif_dict)
        else:
            exif_bytes = None

        # Save the image with EXIF metadata
        image.save(filepath, format="JPEG", exif=exif_bytes, quality=quality)
    else:
        raise ValueError("Unsupported format. Use 'PNG' or 'JPEG'.")

def export_images(arrays, capture_config, image_metadata, camera_metadata, output_path,name_append = ""):
    print("exporting")

    # Save metadata
    with open(os.path.join(output_path, "image_metadata" + name_append + ".txt"), "w") as fp:
        json.dump(image_metadata, fp)
        # Save metadata
    with open(os.path.join(output_path, "camera_metadata" + name_append + ".txt"), "w") as fp:
        json.dump(camera_metadata, fp)

#  (arrays[0], os.path.join(output_path, "image.png"), metadata, [capture_config, "main"], "PNG"),

    # Define image-saving tasks
    tasks = [
        (arrays[0], os.path.join(output_path, "image" + name_append + ".png"), image_metadata, [capture_config, "main"], "PNG"),#"JPG", 95),
        (arrays[1], os.path.join(output_path, "lores" + name_append + ".jpg"), image_metadata, [capture_config, "lores"], "JPG", 95),
    ]

    # Use ThreadPoolExecutor for parallel saving
    def save_task(args):
        save_image_with_metadata(*args)

    with ThreadPoolExecutor() as executor:
        executor.map(save_task, tasks)

    print("done exporting")

def sort_dict(d):
    d_keys = list(d.keys())
    d_keys.sort()
    d = {i: d[i] for i in d_keys}
    return d

def s(tmp):
    plt.imshow(tmp)
    plt.show(block = True)

output_path = os.path.join(os.path.dirname(os.path.realpath(__name__)),'images')
os.makedirs(output_path,exist_ok=True)

use_preview = True

picam2 = Picamera2()

if use_preview:
    picam2.start_preview(Preview.QTGL,x=1280,y=1, width = 640, height = 480)

# not using raw formats as they are still not fully documented
capture_config = picam2.create_still_configuration(
    main= {"format": "RGB888", "size": (4056,3040)},    # for outputs
    lores = {"format": "XBGR8888","size":(640,480)},    # for display
    # raw={'format': 'SRGGB12', "size": (4056,3040)},
    display = "lores",
    buffer_count=1)
# picam2.configure(capture_config)
preview_config = picam2.create_preview_configuration(
    main= {"format": "RGB888", "size": (4056,3040)},
    lores = {"format": "XBGR8888","size":(640,480)}, 
    # raw={"format": "SRGGB12", "size": (4056,3040)},
    display = "lores"
)
picam2.configure(preview_config)
main_camera_stream_config = capture_config['main']

# open the default image metadata and read in the settings as a sorted dict
with open("camera_settings.txt") as f:
    default_image_settings = f.read()
default_image_settings = json.loads(default_image_settings)
default_image_settings = sort_dict(default_image_settings)

# apply the default settings to the current camera
for key in default_image_settings:
    try:
        picam2.set_controls({key:default_image_settings[key]})
    except:
        print('FAIL to set camera setting')
        print(key,default_image_settings[key])

exp_time = 1/10
exp_time_us = int(round(exp_time * 1000000))
picam2.set_controls({"ExposureTime": exp_time_us}) # overwrite the exposre for testing
        
picam2.start()
time.sleep(0.1)
picam2.title_fields = ["ExposureTime","AnalogueGain"] # v"ExposureTime","AnalogueGain","DigitalGain",
time.sleep(0.1)

# Clean the output folder
files = glob.glob(os.path.join(output_path, "*"))
for f in files:
    os.remove(f)

print('capturing data')
arrays, metadata = picam2.switch_mode_and_capture_arrays(capture_config, ["main","lores"])
camera_metadata = main_camera_stream_config
metadata["ISO"] = round(100*metadata["AnalogueGain"])
export_images(arrays,capture_config,metadata,camera_metadata,output_path)


while True:
    wait_time = 30
    print("waiting for", wait_time, '(s)')
    time.sleep(wait_time)

    print('capturing data')
    arrays, metadata = picam2.switch_mode_and_capture_arrays(capture_config, ["main","lores"])
    camera_metadata = main_camera_stream_config
    metadata["ISO"] = round(100*metadata["AnalogueGain"])
    export_images(arrays,capture_config,metadata,camera_metadata,output_path,name_append="2")

print('EOF')

