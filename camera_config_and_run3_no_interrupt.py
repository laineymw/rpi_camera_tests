from concurrent.futures import ThreadPoolExecutor
import os, time, datetime, subprocess
import glob
import json
import piexif
# from PIL import Image, PngImagePlugin
import numpy as np
from picamera2 import Picamera2, Preview
# from pprint import pprint
# import matplotlib.pyplot as plt

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
        (arrays[0], os.path.join(output_path, "image" + name_append + ".jpg"), image_metadata, [capture_config, "main"],"JPG", 95),
        (arrays[1], os.path.join(output_path, "lores" + name_append + ".jpg"), image_metadata, [capture_config, "lores"], "JPG", 95),
    ]

    # Use ThreadPoolExecutor for parallel saving
    def save_task(args):
        save_image_with_metadata(*args)

    with ThreadPoolExecutor() as executor:
        executor.map(save_task, tasks)

    print("done exporting")

def process_raw(input_array,R = False, G = False, G1 = False, G2 = False, B = False, RGB = True, RGB2 = False):
    if 'uint16' not in str(input_array.dtype):
        input_array = input_array.view(np.uint16)

    if R or G or B or G1 or G2 or RGB2:
        RGB = False

    if RGB:
        blue_pixels = input_array[0::2,0::2]
        red_pixels = input_array[1::2,1::2]
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        avg_green = ((green1_pixels+green2_pixels)/2).astype(np.uint16)

        out = np.stack((red_pixels,avg_green,blue_pixels),axis = -1)
    if R:
        out = input_array[1::2,1::2]
    if G:
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        out = ((green1_pixels+green2_pixels)/2).astype(np.uint16)
    if G1:
        out = input_array[0::2,1::2]
    if G2:
        out = input_array[1::2,0::2]
    if B:
        out = input_array[0::2,0::2]
    if RGB2:
        blue_pixels = input_array[0::2,0::2]
        red_pixels = input_array[1::2,1::2]
        green1_pixels = input_array[0::2,1::2]
        green2_pixels = input_array[1::2,0::2]

        a = np.concatenate((blue_pixels,green1_pixels),axis = 0)
        b = np.concatenate((green2_pixels,red_pixels), axis = 0)
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

    picam2 = Picamera2()

    cam_config = picam2.create_preview_configuration(
        main= {"format": "RGB888", "size": (2028,1520)},
        lores = {"format": "XBGR8888","size":(640,480)}, 
        raw={"format": "SRGGB12", "size": (2028,1520)},#(4056,3040)},
        display = "lores",buffer_count=1
    )
    picam2.configure(cam_config)

    if use_preview:
        if monitor_size:
            picam2.start_preview(Preview.QTGL,x=monitor_size[0]-cam_config['lores']['size'][0]
                                ,y=1, width = cam_config['lores']['size'][0],
                                height = cam_config['lores']['size'][1])
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
        except:
            print('FAIL to set camera setting')
            print(key,default_image_settings[key])

    exp_time = 1/30
    exp_time_us = int(round(exp_time * 1000000))
    picam2.set_controls({"ExposureTime": exp_time_us}) # overwrite the exposre for testing

    AnalogueGain = 8.0
    picam2.set_controls({'AnalogueGain': AnalogueGain}) # overwrite analog gain
            
    picam2.start()
    time.sleep(0.5)
    picam2.title_fields = ["ExposureTime","AnalogueGain"] # v"ExposureTime","AnalogueGain","DigitalGain",
    time.sleep(0.5)

    # Clean the output folder
    files = glob.glob(os.path.join(output_path, "*"))
    for f in files:
        os.remove(f)

    print('capturing data')
    arrays, metadata = picam2.capture_arrays(["main","lores"])
    camera_metadata = main_camera_stream_config
    metadata["ISO"] = round(100*metadata["AnalogueGain"])
    # export_images(arrays,cam_config,metadata,camera_metadata,output_path)

    # plt.ion()
    # fig, ax = plt.subplots()

    # Variables for FPS calculation
    start_time = time.time()
    frame_count = 0
    fps_update_interval = 5  # Seconds
    loop_counter = 0
    loop_counter_max = 100

    while True:

        # print('capturing data')

        arrays, metadata = picam2.capture_arrays(["raw"]) #"main","lores","raw"
        camera_metadata = main_camera_stream_config
        metadata["ISO"] = round(100*metadata["AnalogueGain"])
        # arrays[2] = arrays[2].view(np.uint16)
        temp_raw = process_raw(arrays[0], G1 = True)

        # # export_images(arrays,cam_config,metadata,camera_metadata,output_path,name_append="2")
        # print('loop', datetime.datetime.now().strftime("%H:%M:%S.%f"))

        # Increment frame count
        frame_count += 1

        # Calculate and print FPS every 5 seconds
        elapsed_time = time.time() - start_time
        if elapsed_time >= fps_update_interval:
            fps = frame_count / elapsed_time
            print(f"FPS: {fps:.2f} --- LOOP: {loop_counter:.0f}")
            start_time = time.time()
            frame_count = 0

            print('Loop', datetime.datetime.now().strftime("%H:%M:%S.%f"))
            loop_counter += 1
            if loop_counter >= loop_counter_max:
                break


    print('EOF')



