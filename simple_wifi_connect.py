import network
import time
from umqtt.simple import MQTTClient
from machine import Pin

# WiFi Credentials
SSID = "Jarvis"
WIFI_PASSWORD = "EncryptThis!!"

# MQTT Credentials
BROKER_ADDRESS = "mqtt.onwords.in"
MQTT_CLIENT_ID = "ESP32_MQTT_Client"
TOPIC_SUB = "onwords/uPython/sub"
TOPIC_PUB = "onwords/uPython/pub"
PORT = 1883  
USERNAME = "Nikhil"
MQTT_PASSWORD = "Nikhil8182"


led = Pin(2, Pin.OUT)      #Led indication for connectivity

# WiFi Connection
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, WIFI_PASSWORD)

    print("Connecting to WiFi", end="")
    timeout = 15 
    while not wlan.isconnected() and timeout > 0:
        print(".", end="")
        led_blink(3, 0.3, 1) 
        timeout -= 3 

    if wlan.isconnected():
        print("\n✅ Connected to WiFi:", wlan.ifconfig())
        return True
    else:
        print("\n❌ WiFi Connection Failed!")
        return False


def led_blink(blinks, delay, pause):
    for _ in range(blinks):
        led.value(1)
        time.sleep(delay)
        led.value(0)
        time.sleep(delay)
    time.sleep(pause)

def on_message(topic, msg):
    print(f"Received: {topic.decode()} -> {msg.decode()}")

# Connect to WiFi
while not connect_wifi():
    pass  

print(f"Connecting to MQTT Broker: {BROKER_ADDRESS}")
mqtt_connected = False
try:
    client = MQTTClient(MQTT_CLIENT_ID, BROKER_ADDRESS, PORT, USERNAME, MQTT_PASSWORD)
    client.set_callback(on_message)
    client.connect()
    client.subscribe(TOPIC_SUB)
    print(f"✅ Connected to MQTT Broker: {BROKER_ADDRESS}")
    mqtt_connected = True
except Exception as e:
    print("❌ MQTT Connection Error:", e)
    mqtt_connected = False

# Main Loop
while True:
    try:
        if mqtt_connected:
            led.value(1)  
        else:
            led_blink(1, 0.5, 0.5)  # ✅ Blink every 1s if WiFi is OK but no MQTT

        client.check_msg()  # Check for incoming messages
        time.sleep(1)
        client.publish(TOPIC_PUB, "ESP32 is online")

    except Exception as e:
        print("Error in MQTT Loop:", e)
        mqtt_connected = False
        led_blink(3, 0.3, 1)  # ✅ If disconnected, blink 3 times every 1s
