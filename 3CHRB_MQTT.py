import esp32
import network
import ujson
import usocket
import usocket as socket
import time
import ubinascii
import urandom
import machine
from machine import Pin, disable_irq, enable_irq
from time import sleep_ms
import uasyncio as asyncio
import struct
from umqtt.simple import MQTTClient

nvs = esp32.NVS("storage")    #Product ID
product_key = "product_id"

client = None 


R1 = Pin(26, Pin.OUT)         #Output relay Pins
R2 = Pin(25, Pin.OUT)
R3 = Pin(33, Pin.OUT)

R1.value(0)                   #Output relay pins initial state
R2.value(0)
R3.value(0)

S_Led = Pin(4, Pin.OUT)       #status Led
S_Led.value(0)

F1 = Pin(17, Pin.IN, Pin.PULL_DOWN)
F2 = Pin(18, Pin.IN, Pin.PULL_DOWN)      #Feedback pins
F3 = Pin(19, Pin.IN, Pin.PULL_DOWN)

Rst = Pin(32, Pin.IN, Pin.PULL_UP)      #reset pin

def get_product_id():
    try:
        buf = bytearray(32)  
        length = nvs.get_blob(product_key, buf)  
        return buf[:length].decode() 
    except OSError:
        return None

product_id = get_product_id()
print(f"stored Product ID:{product_id}")

BROKER_ADDRESS = "mqtt.onwords.in"
MQTT_CLIENT_ID = product_id
TOPIC_SUB = f"onwords/{product_id}/status"
TOPIC_PUB = f"onwords/{product_id}/currentStatus"
PORT = 1883  
USERNAME = "Nikhil"
MQTT_PASSWORD = "Nikhil8182"

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid=f"onwords-{product_id}", authmode=network.AUTH_OPEN)  

while ap.active() is False:
    time.sleep(1)
print("AP Mode Active. IP Address:", ap.ifconfig()[0])

def get_stored_wifi_credentials():
    """Retrieves WiFi credentials from NVS."""
    try:
        ssid_buf = bytearray(38)
        pass_buf = bytearray(38)

        if nvs.get_blob("wifi_ssid", ssid_buf) and nvs.get_blob("wifi_password", pass_buf):
            stored_ssid = ssid_buf.decode().strip("\x00")
            stored_password = pass_buf.decode().strip("\x00")
            return stored_ssid, stored_password
    except:
        pass

    return None, None


def connect_wifi(ssid, password):
    """Connects to the Wi-Fi network."""
    wifi.connect(ssid, password)
    
    for _ in range(15):  # Wait for connection (15 attempts)
        if wifi.isconnected():
            print("Connected to WiFi:", ssid)
            print("IP Address:", wifi.ifconfig()[0])
            
            ap.active(False)
            print("SoftAP Mode Disabled.")
            return True
        time.sleep(2)  # Wait before checking again
    
    print("WiFi connection failed!")
    return False

def handle_request(conn):
    """Handles incoming HTTP requests."""
    try:
        request = conn.recv(1024).decode()
        print("Received Request:\n", request)

        if "POST /" in request:
            json_data = request.split("\r\n\r\n")[-1]  # Extract JSON body
            credentials = ujson.loads(json_data)

            ssid = credentials.get("ssid")
            password = credentials.get("password")

            if ssid and password:
                nvs.set_blob("wifi_ssid", ssid.encode())
                nvs.set_blob("wifi_password", password.encode())
                nvs.commit()
                print(f"WiFi credentials stored: SSID={ssid}, Password={password}")

                conn.send("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nCredentials Saved. Restarting...")
                conn.close()
                time.sleep(2)  # Give time to send response before restarting

                machine.reset()  # Restart ESP32 to apply new credentials
    except Exception as e:
        print("Error handling request:", e)
        conn.send("HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid Request")
        conn.close()

def start_http_server():
    """Starts a simple HTTP server to receive Wi-Fi credentials."""
    addr = ("0.0.0.0", 8182)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(5)
    print("HTTP Server started on 192.168.4.1:8182")

    while True:
        conn, addr = s.accept()
        print(f"Connection established with {addr}")
        handle_request(conn)
        
def mqtt_callback(topic, msg):
    print(f"Received from {topic.decode()}: {msg.decode()}")
    data = ujson.loads(msg)
    if "device1" in data:
        R1.value(data["device1"])
    if "device2" in data:
        R2.value(data["device2"])
    if "device3" in data:
        R3.value(data["device3"])

def connect_mqtt():
    global client
    client = MQTTClient(client_id=product_key, server=BROKER_ADDRESS, port=PORT, user=USERNAME, password=MQTT_PASSWORD)
    client.set_callback(mqtt_callback)
    client.connect()
    client.subscribe(TOPIC_SUB)
    print(f"Subscribed to {TOPIC_SUB}")
    return client


def publish_state():
    global client  # Ensure we're referencing the global client
    if client:  # Check if the client is connected
        state = {
            "device1": R1.value(),
            "device2": R2.value(),
            "device3": R3.value()
        }
        client.publish(TOPIC_PUB, ujson.dumps(state))
        print("Published state:", state)
    else:
        print("MQTT client not connected!")

def handle_F1(pin):
    R1.value(not R1.value())  # Toggle R1
    publish_state()

def handle_F2(pin):
    R2.value(not R2.value())  # Toggle R2
    publish_state()

def handle_F3(pin):
    R3.value(not R3.value())  # Toggle R3
    publish_state()

F1.irq(trigger=Pin.IRQ_RISING, handler=handle_F1)
F2.irq(trigger=Pin.IRQ_RISING, handler=handle_F2)
F3.irq(trigger=Pin.IRQ_RISING, handler=handle_F3)     

stored_ssid, stored_password = get_stored_wifi_credentials()

if stored_ssid and stored_password:
    print(f"Trying to connect to stored Wi-Fi: {stored_ssid}")
    if connect_wifi(stored_ssid, stored_password):
        print("Connected successfully!")
        
        time.sleep(2)
        # Try connecting to MQTT Broker
        mqtt_client = connect_mqtt()
        try:
            while True: 
                mqtt_client.check_msg()  # Check for new MQTT messages
                time.sleep(1)
        except KeyboardInterrupt:
            print("Program stopped")
            mqtt_client.disconnect()
        
    else:
        print("Wi-Fi disconnected. trying to reconnect....")
        connect_wifi(stored_ssid, stored_password)
else:
    print("No stored Wi-Fi credentials found. Starting HTTP server...")
    start_http_server()
