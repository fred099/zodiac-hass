#!/usr/bin/env python3
"""Upload MicroPython files to Pico W via serial raw REPL."""

import serial
import serial.tools.list_ports
import time
import sys
import os

BAUDRATE = 115200
PICO_FILES = [
    "pico/boot.py",
    "pico/config.py",
    "pico/zodiac_tri.py",
    "pico/mqtt_ha.py",
    "pico/main.py",
]


def find_pico_port():
    """Auto-detect Pico W serial port."""
    for port in serial.tools.list_ports.comports():
        if "usbmodem" in port.device or "Pico" in (port.description or ""):
            return port.device
    return None


def raw_repl_exec(ser, code, timeout=5):
    """Execute code in MicroPython raw REPL. Returns output string."""
    ser.write(code.encode())
    ser.write(b"\x04")  # Ctrl-D = execute
    time.sleep(0.1)

    # Read until OK marker or timeout
    start = time.time()
    buf = b""
    while time.time() - start < timeout:
        if ser.in_waiting:
            buf += ser.read(ser.in_waiting)
        else:
            time.sleep(0.05)

    return buf.decode("utf-8", errors="replace")


def enter_raw_repl(ser):
    """Interrupt running program and enter raw REPL mode."""
    ser.write(b"\x03")  # Ctrl-C
    time.sleep(0.3)
    ser.write(b"\x03")  # Ctrl-C again
    time.sleep(0.3)
    ser.read(ser.in_waiting)  # clear buffer

    ser.write(b"\x01")  # Ctrl-A = raw REPL
    time.sleep(0.5)
    resp = ser.read(ser.in_waiting)
    if b"raw REPL" in resp:
        print("Entered raw REPL mode")
        return True
    # Try once more
    ser.write(b"\x01")
    time.sleep(0.5)
    resp = ser.read(ser.in_waiting)
    print("Raw REPL mode" + (" OK" if b"raw REPL" in resp else " (assuming OK)"))
    return True


def exit_raw_repl(ser):
    """Exit raw REPL back to normal REPL."""
    ser.write(b"\x02")  # Ctrl-B
    time.sleep(0.3)
    ser.read(ser.in_waiting)


def upload_file(ser, local_path, remote_name):
    """Upload a single file to Pico filesystem via raw REPL."""
    with open(local_path, "r") as f:
        content = f.read()

    print("  %s (%d bytes)..." % (remote_name, len(content)))

    code = "f = open('%s', 'w')\nf.write(%s)\nf.close()\nprint(len(%s))\n" % (
        remote_name, repr(content), repr(content)
    )
    resp = raw_repl_exec(ser, code, timeout=5)

    if "Traceback" in resp or "Error" in resp:
        print("    FAILED: %s" % resp.strip())
        return False

    print("    OK")
    return True


def verify_file(ser, remote_name, expected_size):
    """Verify uploaded file exists and has correct size."""
    code = "import os; print(os.stat('%s')[6])\n" % remote_name
    resp = raw_repl_exec(ser, code, timeout=3)
    return str(expected_size) in resp


def main():
    # Determine port
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = find_pico_port()
        if not port:
            print("No Pico W found. Specify port: python upload.py /dev/cu.usbmodemXXXX")
            sys.exit(1)

    # Determine files to upload
    files = PICO_FILES
    if len(sys.argv) > 2:
        files = sys.argv[2:]

    # Check files exist
    for f in files:
        if not os.path.exists(f):
            print("File not found: %s" % f)
            sys.exit(1)

    print("Connecting to %s..." % port)
    ser = serial.Serial(port, BAUDRATE, timeout=2)
    time.sleep(0.5)

    enter_raw_repl(ser)

    print("\nUploading %d files:\n" % len(files))
    failed = []
    for filepath in files:
        remote = os.path.basename(filepath)
        if not upload_file(ser, filepath, remote):
            failed.append(filepath)

    if failed:
        print("\nFailed uploads: %s" % ", ".join(failed))
    else:
        print("\nAll files uploaded successfully!")

    exit_raw_repl(ser)

    if not failed:
        print("\nReset Pico W to start? (y/n): ", end="")
        try:
            if input().strip().lower() == "y":
                enter_raw_repl(ser)
                raw_repl_exec(ser, "import machine; machine.reset()\n")
                print("Pico W resetting...")
        except (EOFError, KeyboardInterrupt):
            pass

    ser.close()


if __name__ == "__main__":
    main()
