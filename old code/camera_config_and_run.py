import os,time,glob,json,piexif
import matplotlib.pyplot as plt
from PIL import Image, PngImagePlugin
import numpy as np
from pprint import pprint

from picamera2 import Picamera2, Preview

def save_image_with_metadata(array, filepath, metadata=None, capture_config=None, format="PNG", quality=95):
    """
    Converts an M, N, 3 RGB NumPy array to a PIL image and saves it with optional metadata.

    Parameters:
        array (np.ndarray): Input image array of size (M, N, 3) in RGB format.
        filepath (str): Output file path for saving the image.
        metadata (dict, optional): Metadata to include in the saved image.
        format (str, optional): Image format, either "PNG" (default) or "JPEG".
        quality (int, optional): Quality for saving JPEG images (default: 95).

    Returns:
        None
    """
    if isinstance(array, np.ndarray):
        if array.ndim == 3 and array.shape[2] > 3:
            array = array[:,:,0:3]

    if not isinstance(array, np.ndarray) or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError("Input must be an M, N, 3 NumPy array in RGB format.")

    # try to convert to BGR
    try:
        color_format = capture_config[0][capture_config[1]]['format']
        if 'RGB' in color_format.upper():
            array = array[:,:,::-1]
            print('RGB')
        if 'BGR' in color_format.upper():
            print('BGR')
            pass
    except:
        'Could not find image format (colorspace RGB/BGR)'

    # Convert the array to a PIL Image
    # assume its a numpy uint8 array
    image = Image.fromarray(array, 'RGB')

    # Save the image with optional metadata
    if format.upper() == "PNG":
        info = PngImagePlugin.PngInfo()
        if metadata:
            for key, value in metadata.items():
                info.add_text(key, str(value))
        image.save(filepath, format="PNG", pnginfo=info)
    elif format.upper() == "JPEG" or format.upper() == "JPG":
        save_kwargs = {"format": "JPEG", "quality": quality}
        if metadata:
            exif_dict = {"Exif": {}, "0th": {}, "1st": {}}

            # Map metadata to EXIF fields
            exif_dict["Exif"][piexif.ExifIFD.ExposureTime] = (metadata.get("ExposureTime", 1), 1)
            exif_dict["Exif"][piexif.ExifIFD.ISOSpeedRatings] = metadata.get("ISO", 100)
            exif_dict["Exif"][piexif.ExifIFD.ImageUniqueID] = str(metadata.get("SensorTimestamp", ""))
            exif_bytes = piexif.dump(exif_dict)

        # Save the image with EXIF metadata
        image.save(filepath, format="JPEG", exif=exif_bytes, quality=quality)
    else:
        raise ValueError("Unsupported format. Use 'PNG' or 'JPEG'.")


def export_images(arrays,capture_config,metadata,output_path):
    print("exporting")
    files = glob.glob(os.path.join(output_path,"*"))
    for f in files:
        os.remove(f)
    with open(os.path.join(output_path,"metadata.txt"),"w") as fp:
        json.dump(metadata, fp)

    save_image_with_metadata(arrays[0], os.path.join(output_path,"image.png"), metadata=metadata, capture_config = [capture_config,"main"])
    save_image_with_metadata(arrays[1], os.path.join(output_path,"lores.jpg"), metadata=metadata, format="JPG", quality=95, capture_config = [capture_config,"lores"])
    print("done exporting")
        

output_path = os.path.join(os.path.dirname(os.path.realpath(__name__)),'images')
os.makedirs(output_path,exist_ok=True)

picam2 = Picamera2()
# print("Sensor modes")
# pprint(picam2.sensor_modes)
# pprint(picam2.sensor_format) 
picam2.start_preview(Preview.QTGL)

# not using raw formats as they are still not fully documented
capture_config = picam2.create_still_configuration(
    main= {"format": "RGB888", "size": (4056,3040)},    # for outputs
    lores = {"format": "XBGR8888","size":(640,480)},    # for display
    # raw={'format': 'SRGGB12', "size": (4056,3040)},
    display = "lores",
    buffer_count=1)
# picam2.configure(capture_config)
preview_config = picam2.create_preview_configuration(
    main= {"format": "RGB888", "size": (2028,1520)},
    lores = {"format": "XBGR8888","size":(640,480)}, 
    # raw={"format": "SRGGB12", "size": (4056,3040)},
    display = "lores"
)
picam2.configure(preview_config)


sensor_config = picam2.camera_configuration()['sensor']
main_camera_stream_config = picam2.camera_configuration()['main']

print("sensor config")
pprint(sensor_config)
print("CURRENTLY set format")
pprint(main_camera_stream_config)

picam2.start()
time.sleep(0.5)

print('capturing data')
arrays, metadata = picam2.switch_mode_and_capture_arrays(capture_config, ["main","lores"])
metadata.update(sensor_config)
metadata.update(main_camera_stream_config)
metadata["ISO"] = round(100*metadata["AnalogueGain"])
export_images(arrays,capture_config,metadata,output_path)

wait_time = 20
print("waiting for", wait_time, '(s)')
time.sleep(wait_time)

print('capturing data')
arrays, metadata = picam2.switch_mode_and_capture_arrays(capture_config, ["main","lores"])
metadata.update(sensor_config)
metadata.update(main_camera_stream_config)
metadata["ISO"] = round(100*metadata["AnalogueGain"])
export_images(arrays,capture_config,metadata,output_path)

print('EOF')

