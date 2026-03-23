"""Configuration for Zodiac TRi Expert Pico W controller."""

# WiFi
WIFI_SSID = "YourSSID"
WIFI_PASSWORD = "YourWiFiPassword"

# MQTT
MQTT_SERVER = "homeassistant.local"
MQTT_USER = "mqtt"
MQTT_PASSWORD = "YourMQTTPassword"

# RS485 (Waveshare Pico-2CH-RS485, Channel 1 = UART1)
RS485_UART_ID = 1
RS485_TX_PIN = 4
RS485_RX_PIN = 5
RS485_BAUDRATE = 9600

# Zodiac TRi
# Default output percent when powered on (0 = off until set from HA)
DEFAULT_PERCENT = 0

# How often to send commands to TRi (seconds)
POLL_INTERVAL = 2

# How often to publish state to MQTT (seconds)
PUBLISH_INTERVAL = 10
