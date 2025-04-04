import cv2
import numpy as np

# cv2 imshow but resized to a size that can fit in a normal monitor size
def imshow_resize(frame_name = "img", frame = 0, resize_size = [640,480], default_ratio = 1.3333,
                  always_on_top = True, use_waitkey = True, move_to = [1920,1]):
   
    frame = cv2.resize(frame, dsize=resize_size)
    cv2.imshow(frame_name, frame)
    if always_on_top:
        cv2.setWindowProperty(frame_name, cv2.WND_PROP_TOPMOST, 1)
    if use_waitkey:
        cv2.waitKey(1)
    if frame_name == "stream":
        move_to = [1920,520]
        cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
    else:
        cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
    return True

# this captures the first N images to clear the pipeline (sometime just black images)
def clear_camera_image_buffer(cap,N=2):
    for i in range(N):
        ret, frame = cap.read()

def list_supported_capture_properties(cap: cv2.VideoCapture):
    """ List the properties supported by the capture device.
    """
    supported = list()
    set_as = list()
    idx = list()
    for i,attr in enumerate(dir(cv2)):
        if attr.startswith('CAP_PROP'):
            if cap.get(getattr(cv2, attr)) != -1:
                supported.append(attr)
                set_as.append(cap.get(getattr(cv2, attr)))
                idx.append(i)
    return supported, set_as, idx

def list_all_potential_cap_APIs():
    list_of_apis = [
        cv2.CAP_ANY,0,
        cv2.CAP_VFW,200,
        cv2.CAP_V4L,200,
        cv2.CAP_FIREWIRE,300,
        cv2.CAP_QT,500,
        cv2.CAP_UNICAP,600,
        cv2.CAP_DSHOW,700,
        cv2.CAP_PVAPI,800,
        cv2.CAP_OPENNI,900,
        cv2.CAP_OPENNI_ASUS,910,
        cv2.CAP_ANDROID,1000,
        cv2.CAP_XIAPI,1100,
        cv2.CAP_AVFOUNDATION,1200,
        cv2.CAP_GIGANETIX,1300,
        cv2.CAP_MSMF,1400,
        cv2.CAP_WINRT,1410,
        cv2.CAP_INTELPERC,1500,
        cv2.CAP_REALSENSE,1500,
        cv2.CAP_OPENNI2,1600,
        cv2.CAP_OPENNI2_ASUS,1610,
        cv2.CAP_OPENNI2_ASTRA,1620,
        cv2.CAP_GPHOTO2,1700,
        cv2.CAP_GSTREAMER,1800,
        cv2.CAP_FFMPEG,1900,
        cv2.CAP_IMAGES,2000,
        cv2.CAP_ARAVIS,2100,
        cv2.CAP_OPENCV_MJPEG,2200,
        cv2.CAP_INTEL_MFX,2300,
        cv2.CAP_XINE,2400,
        cv2.CAP_UEYE,2500,
        cv2.CAP_OBSENSOR,2600]
   
    supported = list()
    for i, this_api in enumerate(list_of_apis):
        if (i % 2) == 0:
            cap = cv2.VideoCapture(0, this_api) # using dshow
            this_supported, set_as, idx = list_supported_capture_properties(cap)
            if np.sum(np.sum(set_as)) != 0.0:
                print(this_api)
                supported.append(this_api)
            cap.release()

    return supported

def split_and_concat(image, mode='RGB'):
    # Split the image into individual color channels
    b, g, r = cv2.split(image)
   
    if mode == 'RGB':
        # Create an array to hold the concatenated images
        stacked_image = np.zeros((image.shape[0], image.shape[1]*3, 3), dtype=np.uint8)
       
        # Assign color channels to the appropriate positions in the array
        stacked_image[:, :image.shape[1]] = cv2.merge([b, np.zeros_like(g), np.zeros_like(r)])  # Blue channel
        stacked_image[:, image.shape[1]:image.shape[1]*2] = cv2.merge([np.zeros_like(b), g, np.zeros_like(r)])  # Green channel
        stacked_image[:, image.shape[1]*2:image.shape[1]*3] = cv2.merge([np.zeros_like(b), np.zeros_like(g), r])  # Red channel
       
        return stacked_image
    elif mode == 'Grayscale':
        # Normalize the grayscale channels
        b_norm = b / max(np.max(b), np.max(g), np.max(r)) * 255
        g_norm = g / max(np.max(b), np.max(g), np.max(r)) * 255
        r_norm = r / max(np.max(b), np.max(g), np.max(r)) * 255
       
        # Create an array to hold the concatenated normalized grayscale images
        stacked_image = np.zeros((image.shape[0], image.shape[1]*3), dtype=np.uint8)
       
        # Concatenate normalized grayscale channels
        stacked_image[:, :image.shape[1]] = b_norm
        stacked_image[:, image.shape[1]:image.shape[1]*2] = g_norm
        stacked_image[:, image.shape[1]*2:image.shape[1]*3] = r_norm
       
        return stacked_image
    elif mode == 'Mono':
        stacked_image = np.zeros_like(image)

        idx = np.argmax(image, axis = -1)

        stacked_image[idx==0,0] = image[idx==0,0]
        stacked_image[idx==1,1] = image[idx==1,1]
        stacked_image[idx==2,2] = image[idx==2,2]

        return stacked_image
    else:
        print("Invalid mode. Please choose 'RGB' or 'Grayscale'.")