import serial
import time

# Connect to GRBL
ser = serial.Serial('/dev/ttyUSB0', 115200)  # Replace COM3 with your port
time.sleep(2)
ser.write(b"\r\n\r\n")  # Wake up GRBL
time.sleep(2)
ser.flushInput()

# Interactive loop
print("Type GRBL commands below. Type 'exit' to quit.")
while True:
    cmd = input(">> ")
    if cmd.lower() == "exit":
        break
    ser.write((cmd + '\n').encode())
    time.sleep(0.1)
    while ser.in_waiting:
        print(ser.readline().decode().strip())

ser.close()