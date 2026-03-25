"""
main.py — Application entry point.
 
Run with:
    python main.py
"""
 
import sys
import atexit
 
import RPi.GPIO as GPIO
from PyQt6.QtWidgets import QApplication
 
from ui import ModernMainWindow
 
LED_PIN = 26
 
 
def cleanup_gpio():
    """Ensure the LED pin is low and GPIO is released on exit."""
    try:
        GPIO.output(LED_PIN, GPIO.LOW)
        GPIO.cleanup()
        print("GPIO cleaned up on exit")
    except Exception:
        pass
 
 
atexit.register(cleanup_gpio)
 
 
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("MiniMax Controller")
    app.setApplicationVersion("1.0")
 
    window = ModernMainWindow()
    window.show()
 
    sys.exit(app.exec())