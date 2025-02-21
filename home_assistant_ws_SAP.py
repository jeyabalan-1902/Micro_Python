import esp32
import network
import usocket
import usocket as socket
import ujson
import time
import ubinascii
import urandom
import machine
from machine import Pin
import uasyncio as asyncio
import struct

# Home Assistant WebSocket API
HA_HOST = "homeassistant.local"
HA_PORT = 8123
HA_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2Mjc4YjllOTY2NTA0ZTk3YmVkOTAxY2UwN2YzYjc5YSIsImlhdCI6MTczODI5NDM5NCwiZXhwIjoyMDUzNjU0Mzk0fQ.Rik_K7Bk4hm2YJgORVmFNW1g49xipJEGoFAgT72_qCA"
message_id = 1

nvs = esp32.NVS("storage")    #Product ID
product_key = "product_id"

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

# Step 2: Initialize WiFi and Configure AP Mode
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid=f"onwords-{product_id}", authmode=network.AUTH_OPEN)  # Now PRODUCT_ID is defined

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


def generate_ws_key():
    random_bytes = bytes([urandom.getrandbits(8) for _ in range(16)])
    return ubinascii.b2a_base64(random_bytes).decode().strip()


def websocket_handshake(sock):
    ws_key = generate_ws_key()  
    handshake = (
        f"GET /api/websocket HTTP/1.1\r\n"
        f"Host: {HA_HOST}:{HA_PORT}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Origin: http://{HA_HOST}:{HA_PORT}\r\n"
        f"\r\n"
    )
    sock.send(handshake.encode())

    response = sock.recv(1024)
    print("Raw handshake response:", response) 
    if b"101 Switching Protocols" in response:
        print("WebSocket handshake successful")
    else:
        print("WebSocket handshake failed:", response)
        return None
    return sock


def send_ws_message(ws, message):
    frame_header = b"\x81"

    message_length = len(message)
    if message_length <= 125:
        frame_header += bytes([message_length])
    elif message_length <= 65535:
        frame_header += bytes([126]) + bytes([(message_length >> 8) & 0xFF]) + bytes([message_length & 0xFF])
    else:
        frame_header += bytes([127]) + bytes([(message_length >> 56) & 0xFF]) + bytes([(message_length >> 48) & 0xFF]) + \
                        bytes([(message_length >> 40) & 0xFF]) + bytes([(message_length >> 32) & 0xFF]) + \
                        bytes([(message_length >> 24) & 0xFF]) + bytes([(message_length >> 16) & 0xFF]) + \
                        bytes([(message_length >> 8) & 0xFF]) + bytes([message_length & 0xFF])

    
    ws.send(frame_header + message.encode())
    print("Sent:", message)

def receive_ws_message(ws):
    try:
        header = ws.recv(2)
        if not header:
            return None

        fin = (header[0] & 0x80) != 0
        opcode = header[0] & 0x0F
        mask = (header[1] & 0x80) != 0
        payload_length = header[1] & 0x7F

        if payload_length == 126:
            payload_length = int.from_bytes(ws.recv(2), "big")
        elif payload_length == 127:
            payload_length = int.from_bytes(ws.recv(8), "big")

        payload = ws.recv(payload_length)
        if mask:
            masking_key = ws.recv(4)
            payload = bytes([payload[i] ^ masking_key[i % 4] for i in range(len(payload))])

        return payload.decode()
    except Exception as e:
        print("Error receiving message:", e)
        return None
    
def connect_ha_websocket():
    print("Connecting to Home Assistant WebSocket...")
    
    sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
    sock.settimeout(5)  
    addr = usocket.getaddrinfo(HA_HOST, HA_PORT)[0][-1]
    
    try:
        sock.connect(addr)
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

    ws = websocket_handshake(sock)
    if not ws:
        return None


    auth_msg = ujson.dumps({"type": "auth", "access_token": HA_AUTH_TOKEN})
    send_ws_message(ws, auth_msg)

    message = receive_ws_message(ws)
    if message:
        print("Received:", message)
        try:
            msg_json = ujson.loads(message)
            if msg_json.get("type") == "auth_ok":
                print("Authentication successful with Home Assistant")
                return ws
            elif msg_json.get("type") == "auth_invalid":
                print("Authentication failed!")
            else:
                print("Unexpected response:", msg_json)
        except Exception as e:
            print("Error parsing response:", e)
    else:
        print("No response received from server")
    
    return None

def subscribe_to_events(ws):
    msg = {"id": 2, "type": "subscribe_events", "event_type": "state_changed"}
    send_ws_message(ws, ujson.dumps(msg))
    print("Subscribed to state change events.")

def send_data(ws, entity_id, state):
    global message_id 
    msg = {
        "id": message_id,
        "type": "call_service",
        "domain": "switch",
        "service": "turn_on" if state == "ON" else "turn_off",
        "service_data": {"entity_id": entity_id}
    }
    send_ws_message(ws, ujson.dumps(msg))
#     message_id += 1
    
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
        
def handle_F1(pin):
    R1.value(not R1.value())  # Toggle R1
    if R1.value == 1:
        send_data(ws, f"switch1.{product_id}", "ON")
    else:
        send_data(ws, f"switch1.{product_id}", "OFF")

def handle_F2(pin):
    R2.value(not R2.value())  # Toggle R2
    if R2.value == 1:
        send_data(ws, f"switch2.{product_id}", "ON")
    else:
        send_data(ws, f"switch2.{product_id}", "OFF")

def handle_F3(pin):
    R3.value(not R3.value())  # Toggle R3
    if R3.value == 1:
        send_data(ws, f"switch3.{product_id}", "ON")
    else:
        send_data(ws, f"switch3.{product_id}", "OFF")

F1.irq(trigger=Pin.IRQ_RISING, handler=handle_F1)
F2.irq(trigger=Pin.IRQ_RISING, handler=handle_F2)
F3.irq(trigger=Pin.IRQ_RISING, handler=handle_F3) 

# Main Execution
stored_ssid, stored_password = get_stored_wifi_credentials()

if stored_ssid and stored_password:
    print(f"Trying to connect to stored Wi-Fi: {stored_ssid}")
    if connect_wifi(stored_ssid, stored_password):
        print("Connected successfully!")
        
        # Try connecting to Home Assistant WebSocket
        ws = connect_ha_websocket()
        if ws:
            print("Connected to Home Assistant WebSocket!")
            subscribe_to_events(ws)
            while True:
                message = receive_ws_message(ws)
                if message:
                    try:
                        msg_json = ujson.loads(message)
                        if "event" in msg_json and "data" in msg_json["event"]:
                            entity_id = msg_json["event"]["data"].get("entity_id")
                            new_state = msg_json["event"]["data"]["new_state"].get("state") if msg_json["event"]["data"].get("new_state") else None
                            
                            if entity_id and new_state:
                                print(f"Received state change: {entity_id} -> {new_state}")

                    except Exception as e:
                        print("Error processing message:", e)
                        
#                 send_data(ws, "switch.meta_4ch_touch_4", "ON")  # Turn on a light
#                 send_data(ws, "switch.meta_4ch_touch_3", "ON")
#                 send_data(ws, "switch.meta_4ch_touch_2", "ON")
#                 send_data(ws, "switch.meta_4ch_touch", "ON")
#                 time.sleep(5)
#                 send_data(ws, "switch.meta_4ch_touch_4", "OFF")  # Turn off light
#                 send_data(ws, "switch.meta_4ch_touch_3", "OFF")
#                 send_data(ws, "switch.meta_4ch_touch_2", "OFF")
#                 send_data(ws, "switch.meta_4ch_touch", "OFF")
#                 time.sleep(5)
    else:
        print("Stored Wi-Fi credentials failed. Starting HTTP server for new credentials.")
        start_http_server()
else:
    print("No stored Wi-Fi credentials found. Starting HTTP server...")
    start_http_server()

