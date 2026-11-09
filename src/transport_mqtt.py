"""MQTT transport: sensors publish sealed messages, the gateway subscribes.

AI-ASSISTED BASE CODE (declare in AI_LOG.md). Team modifications: [list here].

Topic layout:  plant/<device_id>/telemetry   payload = sealed blob (see crypto_modes.py)
Requires:      pip install paho-mqtt    and a broker, e.g. Mosquitto on localhost:1883
"""
import threading

import paho.mqtt.client as mqtt

TOPIC_FMT = "plant/{device}/telemetry"
TOPIC_FILTER = "plant/+/telemetry"


def _device_from_topic(topic):
    return topic.split("/")[1]


class SensorPublisher:
    def __init__(self, host="localhost", port=1883):
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.connect(host, port, keepalive=30)
        self._client.loop_start()

    def publish(self, device_id, blob):
        info = self._client.publish(TOPIC_FMT.format(device=device_id), blob, qos=1)
        info.wait_for_publish(timeout=5)

    def close(self):
        self._client.loop_stop()
        self._client.disconnect()


class GatewaySubscriber:
    """Calls on_blob(device_id, blob) for every message received on the telemetry topics."""

    def __init__(self, on_blob, host="localhost", port=1883):
        self._on_blob = on_blob
        self._lock = threading.Lock()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_message = self._handle
        self._client.connect(host, port, keepalive=30)
        self._client.subscribe(TOPIC_FILTER, qos=1)
        self._client.loop_start()

    def _handle(self, client, userdata, msg):
        with self._lock:
            self._on_blob(_device_from_topic(msg.topic), msg.payload)

    def close(self):
        self._client.loop_stop()
        self._client.disconnect()
