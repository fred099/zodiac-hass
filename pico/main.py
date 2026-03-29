"""
Main application: Zodiac TRi Expert RS485 controller for Home Assistant.
Runs on Raspberry Pi Pico W with Waveshare Pico-2CH-RS485.
"""

import time
import network
import machine

from config import (
    WIFI_SSID, WIFI_PASSWORD,
    MQTT_SERVER, MQTT_USER, MQTT_PASSWORD,
    RS485_UART_ID, RS485_TX_PIN, RS485_RX_PIN, RS485_BAUDRATE,
    DEFAULT_PERCENT, POLL_INTERVAL, PUBLISH_INTERVAL,
)
from zodiac_tri import ZodiacTri
from mqtt_ha import MqttHA


def connect_wifi():
    """Connect to WiFi with timeout and retry."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    time.sleep(1)  # Let WiFi chip initialize after reset

    for attempt in range(3):
        wlan.disconnect()
        time.sleep(0.5)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        start = time.time()
        while not wlan.isconnected():
            if time.time() - start >= 15:
                print("WiFi attempt %d timed out" % (attempt + 1))
                break
            time.sleep(1)
            print("Connecting to WiFi...")
        if wlan.isconnected():
            print("WiFi connected:", wlan.ifconfig())
            return True
        wlan.active(False)
        time.sleep(2)
        wlan.active(True)
        time.sleep(1)

    print("WiFi failed after 3 attempts")
    return False


def main():
    # Connect WiFi
    if not connect_wifi():
        print("WiFi failed, resetting in 10s...")
        time.sleep(10)
        machine.reset()

    # Initialize RS485 interface to Zodiac TRi
    tri = ZodiacTri(
        uart_id=RS485_UART_ID,
        tx_pin=RS485_TX_PIN,
        rx_pin=RS485_RX_PIN,
        baudrate=RS485_BAUDRATE,
    )
    tri.desired_percent = DEFAULT_PERCENT
    tri.send_interval = POLL_INTERVAL

    # Initialize MQTT with HA discovery
    mqtt = MqttHA(MQTT_SERVER, MQTT_USER, MQTT_PASSWORD)

    # Set up command callbacks
    def on_set_percent(val):
        print("Setting output to %d%%" % val)
        tri.desired_percent = max(0, min(100, val))
        tri.boost = False

    def on_set_boost(val):
        print("Boost: %s" % val)
        tri.boost = val

    last_percent = [DEFAULT_PERCENT]

    def on_set_power(val):
        print("Power: %s" % val)
        if val:
            tri.desired_percent = last_percent[0]
        else:
            if tri.desired_percent > 0:
                last_percent[0] = tri.desired_percent
            tri.desired_percent = 0
            tri.boost = False

    mqtt.on_set_percent = on_set_percent
    mqtt.on_set_boost = on_set_boost
    mqtt.on_set_power = on_set_power

    if not mqtt.connect():
        print("MQTT failed, resetting in 10s...")
        time.sleep(10)
        machine.reset()

    # Initial probe
    print("Probing Zodiac TRi...")
    if tri.probe():
        print("TRi found!")
        device_id = tri.get_id()
        if device_id:
            print("Device ID: %s" % device_id)
    else:
        print("TRi not found on RS485 (will keep trying)")

    # Main loop
    last_publish = 0
    print("Starting main loop")

    while True:
        try:
            # Check for MQTT commands
            mqtt.check_msg()

            # Send command to TRi and get response
            tri.update()

            # Publish state periodically
            now = time.time()
            if now - last_publish >= PUBLISH_INTERVAL:
                last_publish = now
                state = tri.get_state_dict()
                mqtt.publish_state(state)
                print("State: pH=%s ORP=%smV salt=%sppm status=%s output=%s%%" % (
                    state['ph_current'], state['orp_current'],
                    state['salt_ppm'], state['status'],
                    state['output_percent']))

            time.sleep(0.1)

        except OSError as e:
            print("Error: %s" % e)
            # Try to reconnect
            if not mqtt.connected:
                time.sleep(5)
                mqtt.reconnect()

        except KeyboardInterrupt:
            print("Stopped")
            break


main()
