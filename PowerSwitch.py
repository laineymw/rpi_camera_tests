from gpiozero import Button
import os

def shutdown():
    os.system("sudo shutdown now")

# GPIO3 (physical pin 5), internal pull-up enabled
button = Button(3, pull_up=True)

# Run shutdown when button is pressed
button.when_pressed = shutdown

# Keep script running
button.wait_for_press()