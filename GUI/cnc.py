"""
cnc.py — Serial communication with GRBL and motion worker thread.
"""

import time
import traceback
import serial

from PyQt6.QtCore import QThread, pyqtSignal


def dlog(msg: str):
    """Write a timestamped debug line to file only — never to stdout/GUI."""
    line = f"{time.strftime('%H:%M:%S')} [DEBUG] {msg}\n"
    try:
        with open("/home/r/rpi_camera_tests/debug.log", "a") as f:
            f.write(line)
    except Exception:
        pass


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
        """Send GRBL Ctrl+X soft reset, then reopen the serial port cleanly.

        After a reset GRBL fully reboots and sends a boot banner. We flush that
        here so send_command always starts with a clean buffer.
        """
        dlog("soft_reset: sending Ctrl+X")
        port     = self.ser.port
        baudrate = self.ser.baudrate

        try:
            self.ser.write(b"\x18")
            time.sleep(0.1)
        except Exception as e:
            dlog(f"soft_reset: write error (continuing): {e}")

        try:
            self.ser.close()
        except Exception as e:
            dlog(f"soft_reset: close error (continuing): {e}")

        time.sleep(0.5)   # give GRBL time to finish rebooting

        dlog("soft_reset: reopening serial port")
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(0.5)

        # Drain the GRBL boot banner ("Grbl 1.1f [...]", "[MSG:...]") from buffer
        dlog("soft_reset: flushing boot banner")
        deadline = time.time() + 3.0
        while time.time() < deadline:
            line = self.ser.readline().decode(errors="replace").strip()
            dlog(f"soft_reset flush: {line!r}")
            if not line:
                break   # timeout with no data — buffer is clear

        dlog("soft_reset: serial port ready")

    # ------------------------------------------------------------------
    # Core command / query helpers
    # ------------------------------------------------------------------

    def wait_for_movement_completion(self, cleaned_line: str):
        """Poll GRBL with '?' until it reports Idle."""
        skip_keywords = ("$X", "$$", "?")
        if any(kw in cleaned_line for kw in skip_keywords):
            dlog(f"wait_for_movement_completion: skipping for {cleaned_line.strip()!r}")
            return

        idle_counter = 0
        time.sleep(0.025)

        while True:
            dlog(f"wait_poll: fd={self.ser.fd} is_open={self.ser.isOpen()}")
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.025)

            self.ser.write(str.encode("?\n"))
            time.sleep(0.025)

            grbl_response = self.ser.readline().decode().strip()
            dlog(f"wait_poll response: {grbl_response!r}")

            if "ok" not in grbl_response.lower():
                if "idle" in grbl_response.lower():
                    idle_counter += 1

            if idle_counter > 0:
                break

            if "alarm" in grbl_response.lower():
                dlog(f"ALARM detected during wait: {grbl_response}")
                return

    def send_command(self, command: str):
        """Send one GRBL command, wait for completion, and return the response."""
        dlog(f"send_command: fd={self.ser.fd} is_open={self.ser.isOpen()} cmd={command.strip()!r}")
        dlog(f"> {command.strip()}")
        time.sleep(0.025)
        self.ser.write(command.encode())
        time.sleep(0.025)

        self.wait_for_movement_completion(command)

        dlog(f"send_command: after wait, fd={self.ser.fd} is_open={self.ser.isOpen()}")

        out = []
        response = ""
        for i in range(50):
            time.sleep(0.001)
            dlog(f"send_command readline #{i}: fd={self.ser.fd}")
            response = self.ser.readline().decode().strip()
            time.sleep(0.001)
            out.append(response)
            dlog(f"send_command readline #{i} response: {response!r}")

            if "error" in response.lower():
                dlog("send_command: error response")
            if "alarm" in response.lower():
                dlog(f"ALARM detected: {response}")
                return "ALARM", out
            if "grbl" in response.lower() and "help" in response.lower():
                dlog("send_command: GRBL reboot banner detected — stopping readline loop")
                break
            if "ok" in response:
                break

        return response, out

    # ------------------------------------------------------------------
    # Position / motion
    # ------------------------------------------------------------------

    def get_current_position(self) -> dict:
        """Query GRBL for the current machine position.

        Returns None if GRBL is in ALARM state or the response is malformed.
        """
        _, out = self.send_command("? \n")
        try:
            # Normal response: "<Idle|MPos:-81.000,-67.000,-17.000|...>"
            mpos = out[0].split("|")[1]
            coords = mpos.split(",")
            coords[0] = coords[0].split(":")[1]
            return {
                "x_pos": float(coords[0]),
                "y_pos": float(coords[1]),
                "z_pos": float(coords[2]),
            }
        except (IndexError, ValueError) as e:
            dlog(f"get_current_position parse error (ALARM?): {out[0]!r} — {e}")
            return None

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
        dlog("home_grbl: sending $H")
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
    """Runs CNC commands in a background thread so the UI stays responsive.

    Emits ``alarm_triggered`` if GRBL reports an ALARM (e.g. limit switch hit).
    The UI is responsible for handling recovery — this thread does not self-recover.
    """

    alarm_triggered = pyqtSignal()

    def __init__(self, cnc: CNCController, command_type: str, command_data=None):
        super().__init__()
        self.cnc = cnc
        self.command_type = command_type
        self.command_data = command_data

    def run(self):
        dlog(f"CNCWorker.run() started — type={self.command_type}")
        try:
            if self.command_type == "jog":
                result = self.cnc.move_XYZ(self.command_data)
                dlog(f"move_XYZ result={result!r}")
                if result == "ALARM":
                    dlog("Emitting alarm_triggered from jog")
                    self.alarm_triggered.emit()

            elif self.command_type == "home":
                self.cnc.home_grbl()

            elif self.command_type == "recover":
                dlog("recover: soft_reset")
                self.cnc.soft_reset()
                time.sleep(0.2)
                dlog("recover: sending $X")
                self.cnc.send_command("$X\n")
                dlog("recover: homing")
                self.cnc.home_grbl()
                dlog("recover: complete")

            else:
                dlog(f"Unknown command type: {self.command_type}")

        except Exception as e:
            tb = traceback.format_exc()
            dlog(f"CNCWorker EXCEPTION (type={self.command_type}):\n{tb}")
            self.alarm_triggered.emit()

        dlog(f"CNCWorker.run() exiting — type={self.command_type}")