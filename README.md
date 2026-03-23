# Zodiac TRi Expert — Home Assistant via MQTT

Control and monitor a **Zodiac TRi Expert** salt chlorinator from Home Assistant using a Raspberry Pi Pico W with RS485.

```
Zodiac TRi Expert  <--RS485-->  Pico W (Waveshare 2CH-RS485)  <--MQTT-->  Home Assistant
```

The Pico W runs MicroPython and acts as a bridge between the TRi's RS485 bus (Jandy AquaLink Tri protocol) and Home Assistant's MQTT broker. Entities are created automatically via [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery).

## Hardware

| Component | Model |
|-----------|-------|
| Chlorinator | Zodiac TRi Expert (TRi 10/18/22/35) |
| Microcontroller | Raspberry Pi Pico W |
| RS485 board | Waveshare Pico-2CH-RS485 |

### Wiring

The Waveshare board sits directly on the Pico W (piggyback). Connect **Channel 1** on the Waveshare board to the TRi's PCB terminal strip (under the pH/ACL module cover):

| Waveshare CH1 | TRi PCB (terminal 7) |
|---------------|----------------------|
| A | A |
| B | B |
| GND | 0V |

> The Waveshare board has hardware-controlled direction (DE/RE) — no extra GPIO needed.

### Pinout (Waveshare Pico-2CH-RS485)

| GPIO | Function |
|------|----------|
| GP0 | UART0 TX (Channel 0, unused) |
| GP1 | UART0 RX (Channel 0, unused) |
| GP4 | UART1 TX (Channel 1 → TRi) |
| GP5 | UART1 RX (Channel 1 ← TRi) |

## Installation

### Prerequisites

- Raspberry Pi Pico W with [MicroPython](https://micropython.org/download/RPI_PICO_W/) installed
- Home Assistant with the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) installed and configured (Settings → Devices & Services → Add Integration → MQTT). An MQTT broker such as [Mosquitto](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md) must be running — the easiest way is to install the **Mosquitto broker** add-on from the Home Assistant Add-on Store.
- Python 3 + `pyserial` on your computer (for uploading)

### Step 1: Flash MicroPython

1. Hold **BOOTSEL** on the Pico W and connect USB
2. Drag the `.uf2` file to the `RPI-RP2` volume
3. Wait for the Pico W to reboot

### Step 2: Install umqtt

Connect to the Pico W via a serial terminal (e.g. `screen /dev/cu.usbmodemXXXX 115200`) and run:

```python
import mip
mip.install("umqtt.simple")
```

### Step 3: Configure

Copy the example config and fill in your credentials:

```bash
cp pico/config.example.py pico/config.py
```

Edit `pico/config.py`:

```python
WIFI_SSID = "YourSSID"
WIFI_PASSWORD = "YourWiFiPassword"
MQTT_SERVER = "homeassistant.local"
MQTT_USER = "mqtt"
MQTT_PASSWORD = "YourMQTTPassword"
```

### Step 4: Upload to Pico W

```bash
pip install pyserial
python upload.py
```

The upload script auto-detects the Pico W serial port. To specify manually:

```bash
python upload.py /dev/cu.usbmodemXXXX
```

To upload specific files only:

```bash
python upload.py /dev/cu.usbmodemXXXX pico/mqtt_ha.py pico/main.py
```

### Step 5: Configure TRi Expert

On the TRi's control panel:

1. Press **MENU**
2. Navigate to **EXT CONTROLLER**
3. Select **AquaLink Tri**
4. Confirm with **SELECT**

### Step 6: Start

1. Ensure the Pico W is running and connected to MQTT
2. Power on / restart the TRi Expert — it scans for an RS485 controller during the **first 20 seconds** after boot

## Home Assistant entities

The following entities are created automatically via MQTT Discovery:

### Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| pH | Current pH level | pH |
| ORP | Current ORP level | mV |
| pH setpoint | Configured pH target | pH |
| ORP setpoint | Configured ORP target | mV |
| Salt level | Pool salt concentration | ppm |
| Status | Operating status (on, no_flow, low_salt, etc.) | — |
| Chlorine production | Current production level | % |

### Controls

| Entity | Type | Description |
|--------|------|-------------|
| Chlorine production | Number (slider) | Set production 0–100% |
| Boost | Switch | 24h super-chlorination |
| Chlorinator | Switch | On/off |

### Diagnostics

| Entity | Type | Description |
|--------|------|-------------|
| Connected | Binary sensor | RS485 connection status |

## File structure

```
pico/
  boot.py              # Minimal boot
  main.py              # Main loop: WiFi → MQTT → RS485 polling
  config.py            # WiFi, MQTT and RS485 settings (not tracked, see config.example.py)
  config.example.py    # Config template
  zodiac_tri.py        # Jandy AquaLink Tri RS485 protocol
  mqtt_ha.py           # MQTT client with HA auto-discovery
upload.py              # Upload script (host → Pico W via USB serial)
```

## RS485 protocol

Communication uses the Jandy AquaLink protocol:

- **Baud:** 9600, 8N1
- **Address:** `0xB0` (AquaLink Tri mode)
- **Packet format:** `DLE STX <dest> <cmd> [data...] <checksum> DLE ETX`
- **Polling:** Pico W sends `SET_PERCENT` (0x11) every 2 seconds
- **Response:** TRi returns a 15-byte packet with pH, ORP, salt level and status

### Status codes

| Code | Meaning |
|------|---------|
| 0x00 | Producing chlorine |
| 0x01 | No flow |
| 0x02 | Low salt |
| 0x04 | High salt |
| 0x08 | Clean cell |
| 0x10 | High current |
| 0x20 | Low voltage |
| 0x40 | Low water temperature |
| 0x80 | Check PCB |

## Troubleshooting

**TRi not found on RS485:**
- Verify TRi is set to "AquaLink Tri" under EXT CONTROLLER menu
- TRi must be restarted after Pico W is running (20s discovery window)
- Check wiring: A↔A, B↔B, GND↔0V

**MQTT connection errors:**
- Verify credentials in `config.py`
- Ensure Home Assistant MQTT integration is enabled
- Check that the Pico W is on the same network

**Pico W won't connect to WiFi:**
- SSID is case-sensitive
- Verify password in `config.py`

## License

MIT
