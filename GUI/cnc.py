"""
cnc.py — Serial communication with GRBL and motion worker thread.
"""

import time
import serial

from PyQt6.QtCore import QThread


# ---------------------------------------------------------------------------
# GRBL serial controller
# ---------------------------------------------------------------------------

class CNCController:
    """Low-level interface to a GRBL CNC controller over serial."""

    def __init__(self, port: str, baudrate: int):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)   # give GRBL time to boot

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def close_connection(self):
        self.ser.close()

    def soft_reset(self):
        """Send GRBL Ctrl+X soft reset and flush buffers."""
        print(">> GRBL SOFT RESET (Ctrl+X)")
        try:
            self.ser.write(b"\x18")
            time.sleep(0.1)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception as e:
            print(f"Reset error: {e}")

    # ------------------------------------------------------------------
    # Core command / query helpers
    # ------------------------------------------------------------------

    def wait_for_movement_completion(self, cleaned_line: str):
        """Poll GRBL with '?' until it reports Idle."""
        skip_keywords = ("$X", "$$", "?")
        if any(kw in cleaned_line for kw in skip_keywords):
            return

        idle_counter = 0
        time.sleep(0.025)

        while True:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.025)

            self.ser.write(str.encode("?\n"))
            time.sleep(0.025)

            grbl_response = self.ser.readline().decode().strip()

            if "ok" not in grbl_response.lower():
                if "idle" in grbl_response.lower():
                    idle_counter += 1

            if idle_counter > 0:
                break

            if "alarm" in grbl_response.lower():
                print("ALARM detected during wait:", grbl_response)
                return

    def send_command(self, command: str):
        """Send one GRBL command, wait for completion, and return the response."""
        print(f"> {command.strip()}")
        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        self.wait_for_movement_completion(command)

        out = []
        response = ""
        for _ in range(50):
            time.sleep(0.001)
            response = self.ser.readline().decode().strip()
            time.sleep(0.001)
            out.append(response)
            print(f"< {response}")

            if "error" in response.lower():
                print("error--------------------------------------------------")
            if "alarm" in response.lower():
                print("ALARM detected:", response)
                return "ALARM", out
            if "ok" in response:
                break

        return response, out

    # ------------------------------------------------------------------
    # Position / motion
    # ------------------------------------------------------------------

    def get_current_position(self) -> dict:
        """Query GRBL for the current machine position."""
        _, out = self.send_command("? \n")
        mpos = out[0].split("|")[1]          # e.g. "MPos:-81.000,-67.000,-17.000"
        coords = mpos.split(",")
        coords[0] = coords[0].split(":")[1]

        return {
            "x_pos": float(coords[0]),
            "y_pos": float(coords[1]),
            "z_pos": float(coords[2]),
        }

    def move_XYZ(self, position: dict, return_position: bool = False):
        """Issue a G1 linear move to the supplied position dict."""
        command = (
            f"G1 X{position['x_pos']} Y{position['y_pos']} "
            f"Z{position['z_pos']} F2500"
        )
        response, _ = self.send_command(command)
        return self.get_current_position() if return_position else response

    # ------------------------------------------------------------------
    # Setup / homing
    # ------------------------------------------------------------------

    def home_grbl(self):
        print("HOMING CNC")
        self.send_command("$H\n")

    def set_up_grbl(self, home: bool = True):
        self.send_command("$X\n")   # unlock
        self.send_command("?\n")    # status check
        if home:
            self.home_grbl()


# ---------------------------------------------------------------------------
# Motion worker thread
# ---------------------------------------------------------------------------

class CNCWorker(QThread):
    """Runs CNC commands in a background thread so the UI stays responsive."""

    def __init__(self, cnc: CNCController, command_type: str, command_data=None):
        super().__init__()
        self.cnc = cnc
        self.command_type = command_type
        self.command_data = command_data

    def run(self):
        try:
            if self.command_type == "jog":
                result = self.cnc.move_XYZ(self.command_data)
            elif self.command_type == "home":
                result = self.cnc.home_grbl()
            else:
                print(f"Unknown command type: {self.command_type}")
                return

            if result == "ALARM":
                raise RuntimeError("Limit switch hit")

        except Exception as e:
            print("THREAD ERROR:", e)
            self._attempt_recovery()

    def _attempt_recovery(self):
        """Try a soft reset + unlock after a limit switch alarm."""
        try:
            print("Limit hit → sending reset")
            self.cnc.soft_reset()
            time.sleep(0.2)
            self.cnc.send_command("$X\n")
        except Exception as reset_error:
            print("Reset failed:", reset_error)