import serial
import time
from pynput import keyboard

# Serial connection settings (modify according to your CNC machine's configuration)
SERIAL_PORT = "/dev/ttyUSB0"  # Change to your CNC machine's port (e.g., '/dev/ttyUSB0' on Linux)
BAUD_RATE = 115200    # Change to match your CNC machine's baud rate

# Step size for each movement (in mm or machine-specific units)
STEP_SIZE = 1.0
STEP_INCREMENT = 0.1  # Increment/decrement value for adjusting step size

# Flag to indicate if the machine is busy
is_busy = False

# Initialize the serial connection
try:
    cnc_serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Allow time for the CNC to initialize
    print(f"Connected to CNC machine on {SERIAL_PORT}")
    # Optional: Set machine to relative positioning
    cnc_serial.write(b"G91\n")
except Exception as ze:
    print(f"Failed to connect to CNC machine: {ze}")
    exit()

# Function to send G-code commands to the CNC machine
def send_command(command):
    global is_busy
    try:
        is_busy = True  # Mark as busy
        cnc_serial.write(f"{command}\n".encode())
        print(f"Sent: {command}")

        # Wait for the machine's response
        while True:
            response = cnc_serial.readline().decode().strip()
            if response:
                print(f"Response: {response}")
                if response.lower() == "ok":  # CNC typically sends "ok" when ready
                    break
                elif "error" in response.lower():  # Handle errors explicitly
                    print(f"Error received: {response}")
                    break
        is_busy = False  # Mark as ready
    except Exception as e:
        is_busy = False  # Reset on error
        print(f"Error sending command: {e}")

# Define key press actions
def on_press(key):
    global STEP_SIZE, is_busy
    if is_busy:
        print("Machine is busy. Please wait.")
        return  # Ignore keypresses if the machine is busy

    try:
        if key == keyboard.Key.up:
            send_command(f"G91 G0 Y{STEP_SIZE}")  # Move Y-axis positive
        elif key == keyboard.Key.down:
            send_command(f"G91 G0 Y-{STEP_SIZE}")  # Move Y-axis negative
        elif key == keyboard.Key.right:
            send_command(f"G91 G0 X-{STEP_SIZE}")  # Move X-axis positive
        elif key == keyboard.Key.left:
            send_command(f"G91 G0 X{STEP_SIZE}")  # Move X-axis negative
        elif hasattr(key, 'char') and key.char == ']':
            send_command(f"G91 G0 Z{STEP_SIZE}")  # Move Z-axis positive
        elif hasattr(key, 'char') and key.char == '[':
            send_command(f"G91 G0 Z-{STEP_SIZE}")  # Move Z-axis negative
        elif hasattr(key, 'char') and key.char == 'h':
            send_command("$H")  # Home all axes
        elif hasattr(key, 'char') and key.char == 'x':
            send_command("$X")  # unlock
        elif hasattr(key, 'char') and key.char == '+':
            STEP_SIZE += STEP_INCREMENT
            print(f"Step size increased to: {STEP_SIZE}")
        elif hasattr(key, 'char') and key.char == '_':
            STEP_SIZE = max(STEP_INCREMENT, STEP_SIZE - STEP_INCREMENT)
            print(f"Step size decreased to: {STEP_SIZE}")
        elif hasattr(key, 'char') and key.char == 'c':
            get_position()  # Output current position
    except AttributeError:
        pass  # Ignore non-character kexhyxs

# Define key release actions (optional, no action here)
def on_release(key):
    if key == keyboard.Key.esc:
        # Stop listener and close the serial connection
        print("Exiting...")
        try:
            cnc_serial.close()
        except Exception as e:
            print(f"Error closing serial connection: {e}")
        return False
   
# Function to get the current machine position
def get_position():
    try:
        cnc_serial.write(b"?\n")  # Send position query command
        time.sleep(0.1)  # Allow some time for response
        while True:
            response = cnc_serial.readline().decode().strip()
            if response:
                print(f"Machine Position Response: {response}")
                if "MPos:" in response:  # Parse machine position
                    pos_data = response.split('|')[0].split(':')[1]
                    x, y, z = map(float, pos_data.split(','))
                    print(f"Current Position -> X: {x}, Y: {y}, Z: {z}")
                    break
    except Exception as e:
        print(f"Error querying position: {e}")

# Main execution with proper cleanup
try:
    print("Use arrow keys to control the CNC machine. Press 'z'/'x' for Z-axis, 'h' to home, '+'/'-' to adjust step size, and 'Esc' to exit.")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
finally:
    try:
        cnc_serial.close()
        print("Serial connection closed.")
    except Exception as e:
        print(f"Error during cleanup: {e}")