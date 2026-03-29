"""
Zodiac TRi Expert RS485 Protocol (Jandy AquaLink Tri)
Communicates with TRi Expert chlorinator via RS485 and publishes to MQTT.
"""

import time
import json
from machine import UART, Pin

# Jandy protocol constants
DLE = 0x10
STX = 0x02
ETX = 0x03
NUL = 0x00

# Device addresses
ADDR_MASTER = 0x00
ADDR_TRI = 0xB0  # AquaLink Tri mode

# Commands
CMD_PROBE = 0x00
CMD_ACK = 0x01
CMD_STATUS = 0x02
CMD_MSG = 0x03
CMD_PERCENT = 0x11
CMD_GETID = 0x14
CMD_PPM = 0x16

# Status codes (bitmask)
STATUS_ON = 0x00
STATUS_NO_FLOW = 0x01
STATUS_LOW_SALT = 0x02
STATUS_HI_SALT = 0x04
STATUS_CLEAN_CELL = 0x08
STATUS_TURNING_OFF = 0x09
STATUS_HIGH_CURRENT = 0x10
STATUS_LOW_VOLTS = 0x20
STATUS_LOW_TEMP = 0x40
STATUS_CHECK_PCB = 0x80

STATUS_NAMES = {
    STATUS_NO_FLOW: "no_flow",
    STATUS_LOW_SALT: "low_salt",
    STATUS_HI_SALT: "high_salt",
    STATUS_CLEAN_CELL: "clean_cell",
    STATUS_HIGH_CURRENT: "high_current",
    STATUS_LOW_VOLTS: "low_voltage",
    STATUS_LOW_TEMP: "low_temperature",
    STATUS_CHECK_PCB: "check_pcb",
}


def calc_checksum(data):
    """Calculate Jandy protocol checksum: sum of all bytes mod 256."""
    return sum(data) & 0xFF


def build_packet(dest, cmd, data=None):
    """Build a Jandy RS485 packet."""
    payload = bytes([DLE, STX, dest, cmd])
    if data:
        payload += bytes(data)
    chk = calc_checksum(payload)
    payload += bytes([chk, DLE, ETX])
    return payload


def parse_packet(raw):
    """
    Parse a received Jandy packet. Returns (dest, cmd, data) or None.
    Expects: DLE STX <dest> <cmd> [data...] <checksum> DLE ETX
    """
    # Find DLE STX header
    start = -1
    for i in range(len(raw) - 1):
        if raw[i] == DLE and raw[i + 1] == STX:
            start = i
            break
    if start < 0:
        return None

    # Find DLE ETX footer
    end = -1
    for i in range(start + 4, len(raw) - 1):
        if raw[i] == DLE and raw[i + 1] == ETX:
            end = i + 2
            break
    if end < 0:
        return None

    packet = raw[start:end]
    if len(packet) < 7:  # minimum: DLE STX dest cmd chk DLE ETX
        return None

    # Verify checksum
    expected_chk = calc_checksum(packet[:-3])
    actual_chk = packet[-3]
    if expected_chk != actual_chk:
        print("Checksum mismatch: expected 0x%02x, got 0x%02x" % (expected_chk, actual_chk))
        return None

    dest = packet[2]
    cmd = packet[3]
    data = packet[4:-3]
    return (dest, cmd, data)


class ZodiacTri:
    """Interface to Zodiac TRi Expert chlorinator via RS485."""

    def __init__(self, uart_id=1, tx_pin=4, rx_pin=5, baudrate=9600):
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx_pin), rx=Pin(rx_pin))
        self.connected = False
        self.device_id = ""

        # State
        self.output_percent = 0
        self.desired_percent = 0
        self.salt_ppm = 0
        self.status_byte = 0xFF
        self.ph_setpoint = 0.0
        self.acl_setpoint = 0
        self.ph_current = 0.0
        self.orp_current = 0
        self.boost = False

        # Timing
        self.last_send = 0
        self.send_interval = 2  # seconds between commands
        self.no_response_count = 0
        self.max_retries = 5

    def _send(self, packet):
        """Send a packet over RS485."""
        self.uart.write(packet)
        time.sleep(0.05)

    def _receive(self, timeout_ms=1000):
        """Receive a packet from RS485 with timeout."""
        start = time.ticks_ms()
        buf = bytearray()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self.uart.any():
                buf.extend(self.uart.read())
                # Check if we have a complete packet
                if len(buf) >= 7:
                    # Look for DLE ETX at the end
                    for i in range(len(buf) - 1):
                        if buf[i] == DLE and buf[i + 1] == ETX:
                            return bytes(buf[:i + 2])
            time.sleep_ms(10)
        return bytes(buf) if buf else None

    def probe(self):
        """Send probe command to check if TRi is present."""
        packet = build_packet(ADDR_TRI, CMD_PROBE)
        self._send(packet)
        response = self._receive()
        if response:
            parsed = parse_packet(response)
            if parsed:
                self.connected = True
                return True
        self.connected = False
        return False

    def get_id(self):
        """Request device identification."""
        packet = build_packet(ADDR_TRI, CMD_GETID, [0x01])
        self._send(packet)
        response = self._receive()
        if response:
            parsed = parse_packet(response)
            if parsed:
                dest, cmd, data = parsed
                # Extract printable ASCII from response
                self.device_id = bytes(b for b in data if 0x20 <= b < 0x7F).decode()
                return self.device_id
        return None

    def set_percent(self, percent):
        """
        Set chlorinator output percentage.
        0-100 = normal, 101 = boost/superchlorinate.
        Returns parsed status data from response.
        """
        percent = max(0, min(101, percent))
        packet = build_packet(ADDR_TRI, CMD_PERCENT, [percent])
        self._send(packet)
        response = self._receive()
        if response:
            parsed = parse_packet(response)
            if parsed:
                self.no_response_count = 0
                self.connected = True
                dest, cmd, data = parsed
                self._parse_tri_response(response)
                return True
        self.no_response_count += 1
        if self.no_response_count >= self.max_retries:
            self.connected = False
        return False

    def _parse_tri_response(self, raw):
        """
        Parse AquaLink Tri extended response (15 bytes).
        Offsets in full packet:
          [0-1] DLE STX
          [2]   source (0x00)
          [3]   cmd (0x16)
          [4-5] unknown
          [6]   PPM (salt * 100)
          [7]   status byte
          [8]   pH setpoint (/ 10.0)
          [9]   ACL setpoint (* 10)
          [10]  current pH (/ 10.0)
          [11]  current ORP (* 10)
          [12]  checksum
          [13-14] DLE ETX
        """
        if len(raw) <= 11:
            # Short packet (AquaPure mode, 11 bytes)
            parsed = parse_packet(raw)
            if parsed:
                dest, cmd, data = parsed
                if len(data) >= 2:
                    self.salt_ppm = data[0] * 100
                    self.status_byte = data[1]
            return

        # Full AquaLink Tri response (15 bytes)
        if len(raw) > 11:
            self.salt_ppm = raw[6] * 100
            self.status_byte = raw[7]
            self.ph_setpoint = raw[8] / 10.0
            self.acl_setpoint = raw[9] * 10
            self.ph_current = raw[10] / 10.0
            self.orp_current = raw[11] * 10

    def get_status_text(self):
        """Get human-readable status."""
        if not self.connected:
            return "offline"
        if self.status_byte == STATUS_ON:
            return "on"
        if self.status_byte == 0xFF:
            return "off"
        # Check bitmask flags
        flags = []
        for bit, name in STATUS_NAMES.items():
            if self.status_byte & bit:
                flags.append(name)
        return ",".join(flags) if flags else "unknown(0x%02x)" % self.status_byte

    def get_state_dict(self):
        """Return current state as dictionary for MQTT publishing."""
        return {
            "connected": self.connected,
            "device_id": self.device_id,
            "output_percent": self.desired_percent,
            "salt_ppm": self.salt_ppm,
            "status": self.get_status_text(),
            "status_byte": self.status_byte,
            "ph_setpoint": self.ph_setpoint,
            "acl_setpoint": self.acl_setpoint,
            "ph_current": self.ph_current,
            "orp_current": self.orp_current,
            "boost": self.boost,
        }

    def update(self):
        """
        Main update loop call. Sends set_percent command
        and processes response. Call this periodically.
        """
        now = time.time()
        if now - self.last_send < self.send_interval:
            return False

        self.last_send = now
        percent = 101 if self.boost else self.desired_percent
        return self.set_percent(percent)
