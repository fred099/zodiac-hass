"""
MQTT client with Home Assistant auto-discovery for Zodiac TRi Expert.
"""

import json
import time
from umqtt.simple import MQTTClient

# HA MQTT Discovery prefix
DISCOVERY_PREFIX = "homeassistant"
DEVICE_ID = "zodiac_tri_expert"
DEVICE_NAME = "Zodiac TRi Expert"


def _device_info():
    """Return HA device info block."""
    return {
        "identifiers": [DEVICE_ID],
        "name": DEVICE_NAME,
        "manufacturer": "Zodiac",
        "model": "TRi Expert",
    }


class MqttHA:
    """MQTT client with Home Assistant auto-discovery."""

    def __init__(self, server, user, password, client_id="zodiac_tri_pico"):
        self.server = server
        self.user = user
        self.password = password
        self.client_id = client_id
        self.client = None
        self.connected = False

        # State topic base
        self.base_topic = "zodiac_tri"

        # Callback for commands
        self.on_set_percent = None
        self.on_set_boost = None
        self.on_set_power = None

    def connect(self):
        """Connect to MQTT broker with retry."""
        for attempt in range(5):
            try:
                self.client = MQTTClient(
                    self.client_id,
                    self.server,
                    user=self.user,
                    password=self.password,
                )
                self.client.set_callback(self._on_message)
                self.client.connect()
                self.connected = True
                print("MQTT connected")
                time.sleep(0.5)
                self._subscribe()
                self._publish_discovery_safe()
                return True
            except OSError as e:
                print("MQTT error: %s, retry %d/5" % (e, attempt + 1))
                self.connected = False
                time.sleep(3)
        return False

    def _on_message(self, topic, msg):
        """Handle incoming MQTT messages."""
        topic = topic.decode()
        msg = msg.decode()
        print("MQTT recv: %s = %s" % (topic, msg))

        if topic == self.base_topic + "/output_percent/set":
            try:
                val = int(float(msg))
                if self.on_set_percent:
                    self.on_set_percent(val)
            except ValueError:
                pass
        elif topic == self.base_topic + "/boost/set":
            if self.on_set_boost:
                self.on_set_boost(msg.lower() in ("on", "1", "true"))
        elif topic == self.base_topic + "/power/set":
            if self.on_set_power:
                self.on_set_power(msg.lower() in ("on", "1", "true"))

    def _subscribe(self):
        """Subscribe to command topics."""
        topics = [
            self.base_topic + "/output_percent/set",
            self.base_topic + "/boost/set",
            self.base_topic + "/power/set",
        ]
        for t in topics:
            self.client.subscribe(t)
            print("Subscribed: %s" % t)

    def _publish_discovery(self):
        """Publish Home Assistant MQTT discovery messages."""
        device = _device_info()

        # Sensors
        sensors = [
            {
                "unique_id": DEVICE_ID + "_ph_current",
                "name": "pH",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.ph_current }}",
                "device_class": "ph",
                "unit_of_measurement": "pH",
                "icon": "mdi:ph",
            },
            {
                "unique_id": DEVICE_ID + "_orp_current",
                "name": "ORP",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.orp_current }}",
                "unit_of_measurement": "mV",
                "icon": "mdi:flash-triangle-outline",
            },
            {
                "unique_id": DEVICE_ID + "_ph_setpoint",
                "name": "pH borvarde",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.ph_setpoint }}",
                "unit_of_measurement": "pH",
                "icon": "mdi:ph",
                "entity_category": "diagnostic",
            },
            {
                "unique_id": DEVICE_ID + "_acl_setpoint",
                "name": "ORP borvarde",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.acl_setpoint }}",
                "unit_of_measurement": "mV",
                "icon": "mdi:flash-triangle-outline",
                "entity_category": "diagnostic",
            },
            {
                "unique_id": DEVICE_ID + "_salt_ppm",
                "name": "Salthalt",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.salt_ppm }}",
                "unit_of_measurement": "ppm",
                "icon": "mdi:shaker-outline",
            },
            {
                "unique_id": DEVICE_ID + "_status",
                "name": "Status",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.status }}",
                "icon": "mdi:information-outline",
            },
            {
                "unique_id": DEVICE_ID + "_output_percent",
                "name": "Klorproduktion",
                "state_topic": self.base_topic + "/state",
                "value_template": "{{ value_json.output_percent }}",
                "unit_of_measurement": "%",
                "icon": "mdi:percent",
            },
        ]

        for sensor in sensors:
            sensor["device"] = device
            uid = sensor["unique_id"]
            topic = "%s/sensor/%s/%s/config" % (DISCOVERY_PREFIX, DEVICE_ID, uid)
            payload = json.dumps(sensor).encode("utf-8")
            self.client.publish(topic, payload, retain=True)
            time.sleep(0.1)

        # Binary sensor: connected
        conn_config = {
            "unique_id": DEVICE_ID + "_connected",
            "name": "Ansluten",
            "state_topic": self.base_topic + "/state",
            "value_template": "{{ 'ON' if value_json.connected else 'OFF' }}",
            "device_class": "connectivity",
            "entity_category": "diagnostic",
            "device": device,
        }
        topic = "%s/binary_sensor/%s/%s_connected/config" % (DISCOVERY_PREFIX, DEVICE_ID, DEVICE_ID)
        self.client.publish(topic, json.dumps(conn_config).encode("utf-8"), retain=True)
        time.sleep(0.1)

        # Number: output percent control
        number_config = {
            "unique_id": DEVICE_ID + "_output_control",
            "name": "Klorproduktion",
            "state_topic": self.base_topic + "/state",
            "value_template": "{{ value_json.output_percent }}",
            "command_topic": self.base_topic + "/output_percent/set",
            "min": 0,
            "max": 100,
            "step": 10,
            "unit_of_measurement": "%",
            "icon": "mdi:water-percent",
            "device": device,
        }
        topic = "%s/number/%s/%s_output_control/config" % (DISCOVERY_PREFIX, DEVICE_ID, DEVICE_ID)
        self.client.publish(topic, json.dumps(number_config).encode("utf-8"), retain=True)
        time.sleep(0.1)

        # Switch: boost mode
        boost_config = {
            "unique_id": DEVICE_ID + "_boost",
            "name": "Boost",
            "state_topic": self.base_topic + "/state",
            "value_template": "{{ 'ON' if value_json.boost else 'OFF' }}",
            "command_topic": self.base_topic + "/boost/set",
            "icon": "mdi:rocket-launch",
            "device": device,
        }
        topic = "%s/switch/%s/%s_boost/config" % (DISCOVERY_PREFIX, DEVICE_ID, DEVICE_ID)
        self.client.publish(topic, json.dumps(boost_config).encode("utf-8"), retain=True)
        time.sleep(0.1)

        # Switch: power on/off
        power_config = {
            "unique_id": DEVICE_ID + "_power",
            "name": "Klorinator",
            "state_topic": self.base_topic + "/state",
            "value_template": "{{ 'ON' if value_json.output_percent > 0 else 'OFF' }}",
            "command_topic": self.base_topic + "/power/set",
            "icon": "mdi:power",
            "device": device,
        }
        topic = "%s/switch/%s/%s_power/config" % (DISCOVERY_PREFIX, DEVICE_ID, DEVICE_ID)
        self.client.publish(topic, json.dumps(power_config).encode("utf-8"), retain=True)

        print("HA discovery published")

    def _publish_discovery_safe(self):
        """Publish discovery one message at a time with error handling."""
        try:
            self._publish_discovery()
        except OSError as e:
            print("Discovery publish error: %s (will retry later)" % e)

    def publish_state(self, state_dict):
        """Publish current state to MQTT."""
        if not self.connected:
            return
        try:
            self.client.publish(
                self.base_topic + "/state",
                json.dumps(state_dict).encode("utf-8"),
                retain=True,
            )
        except OSError as e:
            print("MQTT publish error: %s" % e)
            self.connected = False

    def check_msg(self):
        """Check for incoming MQTT messages."""
        if not self.connected:
            return
        try:
            self.client.check_msg()
        except OSError as e:
            print("MQTT check_msg error: %s" % e)
            self.connected = False

    def reconnect(self):
        """Attempt to reconnect to MQTT."""
        try:
            self.client.connect()
            self.connected = True
            self._subscribe()
            return True
        except OSError:
            self.connected = False
            return False
