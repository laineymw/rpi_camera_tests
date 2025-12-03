import cv2, os, tqdm, glob, time, datetime, math
# from numpy import zeros, logical_and, logical_or, logical_xor
import numpy as np

def convert_to_float(frac_str):
    try:
        return float(frac_str)
    except ValueError:
        num, denom = frac_str.split('/')
        try:
            leading, num = num.split(' ')
            whole = float(leading)
        except ValueError:
            whole = 0
        frac = float(num) / float(denom)
        return whole - frac if whole < 0 else whole + frac

# cv2 imshow but resized to a size that can fit in a normal monitor size
def imshow_resize(frame_name = "img", frame = 0, resize_size = [640,480], default_ratio = 1.3333,
                  always_on_top = True, use_waitkey = True, move_to = [1920,1]):

    if 'uint8' in str(frame.dtype):
        frame = cv2.resize(frame, dsize=resize_size)
        cv2.imshow(frame_name, frame)
        if always_on_top:
            cv2.setWindowProperty(frame_name, cv2.WND_PROP_TOPMOST, 1)
        if use_waitkey:
            cv2.waitKey(1)
        # if frame_name == "stream":
        #     move_to = [1920-640,1]
        #     cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
        if move_to:
            cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
        else:
            cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
        return True
    else:
        frame = cv2.resize(frame, dsize=resize_size)
        frame = norm_to_uint8(frame)
        cv2.imshow(frame_name, frame)
        if always_on_top:
            cv2.setWindowProperty(frame_name, cv2.WND_PROP_TOPMOST, 1)
        if use_waitkey:
            cv2.waitKey(1)
        # if frame_name == "stream":
        #     move_to = [1920-640,1]
        #     cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
        if move_to:
            cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
        else:
            cv2.moveWindow(frame_name,move_to[0]-resize_size[0],move_to[1])
        return True

# this deletes all the dir contents, recursive or not
def del_dir_contents(path_to_dir, recursive = False):
    if recursive:
        files = glob.glob(os.path.join(path_to_dir,'**/*'), recursive=recursive)
        for f in files:
            if not os.path.isdir(f):
                os.remove(f)
    else: # default
        files = glob.glob(os.path.join(path_to_dir,'*'))
        for f in files:
            os.remove(f)

def norm_to_uint8(a, b_max = None):
    b = a.astype(np.float64)
    if b_max == None:
        b_max = b.max()
    b = 255*(b/b_max)
    b = b.astype(np.uint8)
    return b

# this is a buffer that continues to capture images until the the specified time has elapsed
# this is because if you use time.sleep() the image taken is buffered and not at the actual elapsed time
def capture_images_for_time(cap,N, show_images = False, move_to = [100,100], resize_size = [640,480], start_time = None):
    if start_time == None:
        start_time = time.time()
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to capture frame.")
            break
        if show_images:
            imshow_resize("stream", frame, resize_size=resize_size, move_to=move_to)
        current_time = time.time()
        if start_time + N < current_time:
            break

# this captures the first N images to clear the pipeline (sometime just black images)
def clear_camera_image_buffer(cap,N=2):
    for i in range(N):
        ret, frame = cap.read()

def capture_single_image_wait_N_seconds(camera_settings,timestart = None, excitation_amount = 9, plate_parameters = None, testing = False, output_dir = None):

    todays_date = datetime.date.today().strftime("%Y-%m-%d")

    if timestart == None:
        timestart = time.time()

    if output_dir == None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'output',plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date)
    else:
        output_dir = os.path.join(output_dir,plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date)
   
    os.makedirs(output_dir,exist_ok=True)
    if testing:
        del_dir_contents(output_dir)

    camera_id = camera_settings['widefield'][0]
    cam_width = float(camera_settings['widefield'][1])
    cam_height = float(camera_settings['widefield'][2])
    cam_framerate = camera_settings['widefield'][3]
    time_between_images_seconds = float(excitation_amount)
    time_of_single_burst_seconds = camera_settings['widefield'][5]
    number_of_images_per_burst = 1
    img_file_format = camera_settings['widefield'][7]
    img_pixel_depth = camera_settings['widefield'][8]

    # Define the text and font settings
    text = plate_parameters['experiment_name'] + '--' + plate_parameters['plate_name'] + '--' + todays_date
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 10.0
    font_color1 = (255, 255, 255)  # white color
    thickness1 = 15
    font_color2 = (0, 0, 0)  # black color for outline
    thickness2 = 50

    # Calculate the position for placing the text
    text_size = cv2.getTextSize(text, font, font_scale, thickness1)[0]
    text_x = (cam_width - text_size[0]) // 2  # Center horizontally
    text_y = 250  # 250 pixels from the top
    text_x2 = text_x-200
    text_y2 = 500

    # time_between_images_seconds = 0 # this is just for testing
    img_file_format = 'png' # slow and lossless but smaller

    # Open the camera0
    cap = cv2.VideoCapture(int(camera_id))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
    cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))

    if not cap.isOpened():
        print("Error: Unable to open camera.")
        exit()

    clear_camera_image_buffer(cap)

    num_images = int(number_of_images_per_burst)
    # Capture a series of images
    for i in tqdm.tqdm(range(num_images)):
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to capture frame.")
            break
       
        current_time_for_filename = datetime.datetime.now().strftime("%Y-%m-%d (%H-%M-%S-%f)")
        image_name = current_time_for_filename + '.' + img_file_format
        image_filename = os.path.join(output_dir, image_name)

        cv2.imwrite(image_filename, frame[:,:,-1])
        # print(f"\nCaptured image {i+1}/{num_images}")

        # Put the text on the image
        cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
        cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
        cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
        cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

        imshow_resize("img", frame, resize_size=[640,480])

        capture_images_for_time(cap,time_between_images_seconds, show_images=True,move_to = [1920,520], start_time = timestart)        # time.sleep(1)

    # Release the camera
    # cv2.destroyAllWindows()
    cap.release()

def simple_capture_data(camera_settings, plate_parameters = None, testing = False, output_dir = None):

    todays_date = datetime.date.today().strftime("%Y-%m-%d")

    if output_dir == None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'output',plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date)
    else:
        output_dir = os.path.join(output_dir,plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date)
   
    os.makedirs(output_dir,exist_ok=True)
    if testing:
        del_dir_contents(output_dir, recursive=testing)

    camera_id = camera_settings['widefield'][0]
    cam_width = float(camera_settings['widefield'][1])
    cam_height = float(camera_settings['widefield'][2])
    cam_framerate = camera_settings['widefield'][3]
    time_between_images_seconds = float(camera_settings['widefield'][4])
    time_of_single_burst_seconds = camera_settings['widefield'][5]
    number_of_images_per_burst = float(camera_settings['widefield'][6])
    img_file_format = camera_settings['widefield'][7]
    img_pixel_depth = camera_settings['widefield'][8]

    # Define the text and font settings
    text = plate_parameters['experiment_name'] + '--' + plate_parameters['plate_name'] + '--' + todays_date
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 10.0
    font_color1 = (255, 255, 255)  # white color
    thickness1 = 15
    font_color2 = (0, 0, 0)  # black color for outline
    thickness2 = 50

    # Calculate the position for placing the text
    text_size = cv2.getTextSize(text, font, font_scale, thickness1)[0]
    text_x = (cam_width - text_size[0]) // 2  # Center horizontally
    text_y = 250  # 250 pixels from the top
    text_x2 = text_x-200
    text_y2 = 500

    # time_between_images_seconds = 2 # this is just for testing
    img_file_format = 'png' # slow and lossless but smaller
    # # img_file_format = 'jpg' # fast but lossy small files
    # # img_file_format = 'bmp' # fastest and lossess huge files

    # Open the camera0
    cap = cv2.VideoCapture(int(camera_id))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
    cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))

    if not cap.isOpened():
        print("Error: Unable to open camera.")
        exit()

    clear_camera_image_buffer(cap)

    num_images = int(number_of_images_per_burst)
    # Capture a series of images
    for i in tqdm.tqdm(range(num_images)):
        start_time = time.time()
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to capture frame.")
            break
       
        current_time_for_filename = datetime.datetime.now().strftime("%Y-%m-%d (%H-%M-%S-%f)")
        image_name = current_time_for_filename + '.' + img_file_format
        image_filename = os.path.join(output_dir, image_name)

        cv2.imwrite(image_filename, frame[:,:,-1])#, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])
        # print(f"\nCaptured image {i+1}/{num_images}")

        # Put the text on the image white with a black background
        cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
        cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
        cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
        cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

        imshow_resize("img", frame, resize_size=[640,480])

        capture_images_for_time(cap,time_between_images_seconds, show_images=True,move_to = [1920,520], start_time = start_time)
        # time.sleep(1)

    # Release the camera
    # cv2.destroyAllWindows()
    cap.release()

def simple_capture_data_single_image(camera_settings, plate_parameters = None, testing = False, output_dir = None, image_file_format = 'png'):

    todays_date = datetime.date.today().strftime("%Y-%m-%d")

    if output_dir == None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'output','calibration')
    else:
        output_dir = os.path.join(output_dir,'calibration')
   
    os.makedirs(output_dir,exist_ok=True)
    if testing:
        del_dir_contents(output_dir, recursive=testing)

    camera_id = camera_settings['widefield'][0]
    cam_width = float(camera_settings['widefield'][1])
    cam_height = float(camera_settings['widefield'][2])
    cam_framerate = camera_settings['widefield'][3]
    time_between_images_seconds = float(camera_settings['widefield'][4])
    time_of_single_burst_seconds = camera_settings['widefield'][5]
    number_of_images_per_burst = float(camera_settings['widefield'][6])
    img_file_format = camera_settings['widefield'][7]
    img_pixel_depth = camera_settings['widefield'][8]

    # Define the text and font settings
    text = plate_parameters['experiment_name'] + '--' + plate_parameters['plate_name'] + '--' + todays_date
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 10.0
    font_color1 = (255, 255, 255)  # white color
    thickness1 = 15
    font_color2 = (0, 0, 0)  # black color for outline
    thickness2 = 50

    # Calculate the position for placing the text
    text_size = cv2.getTextSize(text, font, font_scale, thickness1)[0]
    text_x = (cam_width - text_size[0]) // 2  # Center horizontally
    text_y = 250  # 250 pixels from the top
    text_x2 = text_x-200
    text_y2 = 500

    # time_between_images_seconds = 2 # this is just for testing
    if img_file_format == 'png':
        img_file_format = 'png' # slow and lossless but smaller
    else:
        img_file_format = image_file_format # fast but lossy small files
    # # img_file_format = 'bmp' # fastest and lossess huge files

    # Open the camera0
    cap = cv2.VideoCapture(int(camera_id))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
    cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))

    if not cap.isOpened():
        print("Error: Unable to open camera.")
        exit()

    clear_camera_image_buffer(cap)

    num_images = 1
    # Capture a series of images
    start_time = time.time()
    ret, frame = cap.read()
    if not ret:
        print("Error: Unable to capture frame.")
   
    current_time_for_filename = datetime.datetime.now().strftime("%Y-%m-%d (%H-%M-%S-%f)")
    image_name = current_time_for_filename + '.' + img_file_format
    image_filename = os.path.join(output_dir, image_name)

    cv2.imwrite(image_filename, frame[:,:,-1])#, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])
    # print(f"\nCaptured image {i+1}/{num_images}")

    # Put the text on the image white with a black background
    cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
    cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
    cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
    cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

    imshow_resize("img", frame, resize_size=[640,480])

    # capture_images_for_time(cap,time_between_images_seconds, show_images=True,move_to = [1920,520], start_time = start_time)
    # time.sleep(1)

    # Release the camera
    # cv2.destroyAllWindows()
    cap.release()

    return image_filename

def simple_capture_data_fluor(camera_settings, plate_parameters = None, testing = False, output_dir = None, cap = None, return_cap = False):

    todays_date = datetime.date.today().strftime("%Y-%m-%d")

    if output_dir == None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'output',plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date)
    else:
        output_dir = os.path.join(output_dir,plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date,'fluorescent_data')
   
    os.makedirs(output_dir,exist_ok=True)
    if testing:
        del_dir_contents(output_dir)

    camera_id = camera_settings['fluorescence'][0]
    # camera_id = 0 #####################################################################################S
    cam_width = float(camera_settings['fluorescence'][1])
    cam_height = float(camera_settings['fluorescence'][2])
    cam_framerate = camera_settings['fluorescence'][3]
    time_between_images_seconds = float(camera_settings['fluorescence'][4])
    time_of_single_burst_seconds = camera_settings['fluorescence'][5]
    number_of_images_per_burst = float(camera_settings['fluorescence'][6])
    img_file_format = camera_settings['fluorescence'][7]
    img_pixel_depth = camera_settings['fluorescence'][8]
    img_color = camera_settings['fluorescence'][9]

    # Define the text and font settings
    text = plate_parameters['experiment_name'] + '--' + plate_parameters['plate_name'] + '--' + todays_date
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 4
    font_color1 = (255, 255, 255)  # white color
    thickness1 = 15
    font_color2 = (0, 0, 0)  # black color for outline
    thickness2 = 50

    # Calculate the position for placing the text
    text_size = cv2.getTextSize(text, font, font_scale, thickness1)[0]
    text_x = (cam_width - text_size[0]) // 2  # Center horizontally
    text_y = 250  # 250 pixels from the top
    text_x2 = text_x-200
    text_y2 = 500

    if cap == None:
        # Open the camera0
        cap = cv2.VideoCapture(int(camera_id))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
        cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))

        if not cap.isOpened():
            print("Error: Unable to open camera.")
            exit()

    # clear_camera_image_buffer(cap, N = 3)

    num_images = int(number_of_images_per_burst)
    # Capture a series of images
    for i in range(num_images): #tqdm.tqdm(range(num_images)):
        start_time = time.time()
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to capture frame.")
            break
       
        # current_time_for_filename = datetime.datetime.now().strftime("%Y-%m-%d (%H-%M-%S-%f)")
        image_subtype = plate_parameters['well_name'] + '_00' + str(i+1)
        image_name = plate_parameters['well_name'] + '_00' + str(i+1) + '_' + '.' + img_file_format#current_time_for_filename + '.' + img_file_format
        image_filename = os.path.join(output_dir, image_name)

        cv2.imwrite(image_filename, frame[:,:,-1])#, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])
        # print(f"\nCaptured image {i+1}/{num_images}")

        # Put the text on the image white with a black background
        cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
        cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
        cv2.putText(frame, image_subtype, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
        cv2.putText(frame, image_subtype, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

        imshow_resize("img", frame, resize_size=[640,480])

    # Release the camera
    # cv2.destroyAllWindows()
    if return_cap:
        return cap
    else:
        cap.release()

def simple_capture_data_fluor_single_image(camera_settings, plate_parameters = None, testing = False, output_dir = None, image_file_format = 'png'):

    todays_date = datetime.date.today().strftime("%Y-%m-%d")

    if output_dir == None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'output','calibration')
    else:
        output_dir = os.path.join(output_dir,'calibration')
   
    os.makedirs(output_dir,exist_ok=True)
    if testing:
        del_dir_contents(output_dir, recursive=testing)

    camera_id = camera_settings['fluorescence'][0]
    camera_id = 0 #####################################################################################S
    cam_width = float(camera_settings['fluorescence'][1])
    cam_height = float(camera_settings['fluorescence'][2])
    cam_framerate = camera_settings['fluorescence'][3]
    time_between_images_seconds = float(camera_settings['fluorescence'][4])
    time_of_single_burst_seconds = camera_settings['fluorescence'][5]
    number_of_images_per_burst = float(camera_settings['fluorescence'][6])
    img_file_format = camera_settings['fluorescence'][7]
    img_pixel_depth = camera_settings['fluorescence'][8]
    img_color = camera_settings['fluorescence'][9]

    # Define the text and font settings
    text = plate_parameters['experiment_name'] + '--' + plate_parameters['plate_name'] + '--' + todays_date
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 4
    font_color1 = (255, 255, 255)  # white color
    thickness1 = 15
    font_color2 = (0, 0, 0)  # black color for outline
    thickness2 = 50

    # Calculate the position for placing the text
    text_size = cv2.getTextSize(text, font, font_scale, thickness1)[0]
    text_x = (cam_width - text_size[0]) // 2  # Center horizontally
    text_y = 250  # 250 pixels from the top
    text_x2 = text_x-200
    text_y2 = 500

    # time_between_images_seconds = 2 # this is just for testing
    img_file_format = 'png' # slow and lossless but smaller
    # # img_file_format = 'jpg' # fast but lossy small files
    # # img_file_format = 'bmp' # fastest and lossess huge files

    # Open the camera0
    cap = cv2.VideoCapture(int(camera_id))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
    cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))

    if not cap.isOpened():
        print("Error: Unable to open camera.")
        exit()

    clear_camera_image_buffer(cap)

    num_images = 1
    # Capture a series of images
    start_time = time.time()
    ret, frame = cap.read()
    if not ret:
        print("Error: Unable to capture frame.")
   
    current_time_for_filename = datetime.datetime.now().strftime("%Y-%m-%d (%H-%M-%S-%f)")
    image_name = current_time_for_filename + '.' + img_file_format
    image_filename = os.path.join(output_dir, image_name)

    cv2.imwrite(image_filename, frame[:,:,-1])#, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])
    # print(f"\nCaptured image {i+1}/{num_images}")

    # Put the text on the image white with a black background
    cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
    cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
    cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
    cv2.putText(frame, current_time_for_filename, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

    imshow_resize("img", frame, resize_size=[640,480])

    # capture_images_for_time(cap,time_between_images_seconds, show_images=True,move_to = [1920,520], start_time = start_time)
    # time.sleep(1)

    # Release the camera
    # cv2.destroyAllWindows()
    cap.release()

    return image_filename


def capture_data_fluor_multi_exposure(camera_settings, plate_parameters = None, testing = False, output_dir = None, cap = None, return_cap = False):

    todays_date = datetime.date.today().strftime("%Y-%m-%d")

    if output_dir == None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'output',plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date)
    else:
        output_dir = os.path.join(output_dir,plate_parameters['experiment_name'],plate_parameters['plate_name'],todays_date,'fluorescent_data')
   
    os.makedirs(output_dir,exist_ok=True)
    if testing:
        del_dir_contents(output_dir)

    camera_id = camera_settings['fluorescence'][0]
    # camera_id = 0 #####################################################################################S
    cam_width = float(camera_settings['fluorescence'][1])
    cam_height = float(camera_settings['fluorescence'][2])
    cam_framerate = camera_settings['fluorescence'][3]
    time_between_images_seconds = float(camera_settings['fluorescence'][4])
    time_of_single_burst_seconds = camera_settings['fluorescence'][5]
    number_of_images_per_burst = float(camera_settings['fluorescence'][6])
    img_file_format = camera_settings['fluorescence'][7]
    img_pixel_depth = camera_settings['fluorescence'][8]
    img_color = camera_settings['fluorescence'][9]
    cam_exposure = camera_settings['fluorescence'][13]

    # convert the cam_exposure time from seconds into 2^x = seconds
    cam_exposure_cv2 = convert_to_float(cam_exposure)
    cam_exposure_cv2 = math.log(cam_exposure_cv2)/math.log(2)
    cam_exposure_cv2 = int(cam_exposure_cv2) ############################### mathmatically this is worng but program wise this gets -4.0 -> -4

    # Define the text and font settings
    text = plate_parameters['experiment_name'] + '--' + plate_parameters['plate_name'] + '--' + todays_date
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 4
    font_color1 = (255, 255, 255)  # white color
    thickness1 = 15
    font_color2 = (0, 0, 0)  # black color for outline
    thickness2 = 50

    # Calculate the position for placing the text
    text_size = cv2.getTextSize(text, font, font_scale, thickness1)[0]
    text_x = (cam_width - text_size[0]) // 2  # Center horizontally
    text_y = 250  # 250 pixels from the top
    text_x2 = text_x-200
    text_y2 = 500

    if cap == None:
        # Open the camera0
        cap = cv2.VideoCapture(int(camera_id))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
        cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))

        if not cap.isOpened():
            print("Error: Unable to open camera.")
            exit()

    current_exposure = cam_exposure_cv2 + 1 # starting exposure should be 1/8 sec -> 1/16 -> 1/32 -> 1/64
    cv2_exposures = [-8,-6,-4,-2]#,-2]#[-2,-4,-6,-8]

    num_images = int(number_of_images_per_burst)
    frames_array = np.zeros(shape=(int(cam_height),int(cam_width),num_images))
    # Capture a series of images
    for i in range(num_images): #tqdm.tqdm(range(num_images)):
        # start_time = time.time()

        # set the exposure to current_exposre, clear the buffer(??), and then capture
        cap.set(cv2.CAP_PROP_EXPOSURE,cv2_exposures[i])
        capture_images_for_time(cap, N = 0.25)
       
        # read the image from the camera buffer
        ret, frame = cap.read()
        frames_array[:,:,i] = frame[:,:,-1]

        # check
        if not ret:
            print("Error: Unable to capture frame.")
            break
       
        current_time_for_filename = datetime.datetime.now().strftime("%Y-%m-%d (%H-%M-%S-%f)")
        image_subtype = plate_parameters['well_name'] + '_00' + str(i+1) + '_' + str(cv2_exposures[i])
        image_name = plate_parameters['well_name'] + '_00' + str(i+1) + '_' + str(cv2_exposures[i]) + '_' + current_time_for_filename + '.' + img_file_format
        image_filename = os.path.join(output_dir, image_name)

        cv2.imwrite(image_filename, frames_array[:,:,i]) #frame[:,:,-1])#, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])

        if i == num_images-1:
            sum_array = np.sum(frames_array,axis = -1)
            out = norm_to_uint8(sum_array, b_max=None)
            # print(f"\nCaptured image {i+1}/{num_images}")
            # cv2.imwrite(image_filename, out) #frame[:,:,-1])#, [int(cv2.IMWRITE_PNG_COMPRESSION), 5])


        if i != num_images-1:
                        # Put the text on the image white with a black background
            cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
            cv2.putText(frame, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
            cv2.putText(frame, image_subtype, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
            cv2.putText(frame, image_subtype, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

            imshow_resize("img", frame, resize_size=[640,480])
        else:
                                    # Put the text on the image white with a black background
            cv2.putText(out, text, (int(text_x), int(text_y)), font, font_scale, font_color2, thickness2) # black
            cv2.putText(out, text, (int(text_x), int(text_y)), font, font_scale, font_color1, thickness1) # white
            cv2.putText(out, image_subtype, (int(text_x2), int(text_y2)), font, font_scale, font_color2, thickness2) # black
            cv2.putText(out, image_subtype, (int(text_x2), int(text_y2)), font, font_scale, font_color1, thickness1) # white

            imshow_resize("img", out, resize_size=[640,480])

    cap.set(cv2.CAP_PROP_EXPOSURE,cam_exposure_cv2)

    # Release the camera
    # cv2.destroyAllWindows()
    if return_cap:
        return cap
    else:
        cap.release()


def capture_fluor_img_return_img(camera_settings, cap = None, return_cap = False, clear_N_images_from_buffer = 3):

    if cap is None:

        cv2_exposures = [-8,-6,-4,-2]#,-2]#[-2,-4,-6,-8]

        cap_release = True

        camera_id = camera_settings['fluorescence'][0]
        camera_id = 0 #####################################################################################S
        cam_width = float(camera_settings['fluorescence'][1])
        cam_height = float(camera_settings['fluorescence'][2])
        cam_framerate = camera_settings['fluorescence'][3]
        time_between_images_seconds = float(camera_settings['fluorescence'][4])
        time_of_single_burst_seconds = camera_settings['fluorescence'][5]
        number_of_images_per_burst = float(camera_settings['fluorescence'][6])
        img_file_format = camera_settings['fluorescence'][7]
        img_pixel_depth = camera_settings['fluorescence'][8]
        img_color = camera_settings['fluorescence'][9]

        # Open the camera0
        cap = cv2.VideoCapture(int(camera_id))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,int(cam_width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT,int(cam_height))
        cap.set(cv2.CAP_PROP_FPS,int(cam_framerate))
        cap.set(cv2.CAP_PROP_EXPOSURE,cv2_exposures[-1])

        if not cap.isOpened():
            print("Error: Unable to open camera.")
            exit()

        if return_cap:
            cap_release = False
       
    else:
        cap_release = False

    if clear_N_images_from_buffer > 0:
        clear_camera_image_buffer(cap, N = clear_N_images_from_buffer)

    num_images = 1
    # Capture a series of images
    ret, frame = cap.read()
    #frame = frame[:,:,-1]
    if not ret:
        print("Error: Unable to capture frame.")

    if cap_release:
        cap.release()

    if return_cap:
        return frame, cap
    else:
        return frame

if __name__ == "__main__":

    print('pass')

