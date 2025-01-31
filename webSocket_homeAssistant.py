import usocket
import ujson
import network
import time
import ubinascii
import urandom

from machine import Pin, disable_irq, enable_irq
from time import sleep_ms

SSID = "Rnd"
PASSWORD = "nikhil8182"

message_id = 1

led = Pin(2, Pin.OUT) 

button_pin4 = Pin(4, Pin.IN, Pin.PULL_UP)
button_pressed = False
press_counter = 0

HA_HOST = "homeassistant.local"  
HA_PORT = 8123
HA_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2Mjc4YjllOTY2NTA0ZTk3YmVkOTAxY2UwN2YzYjc5YSIsImlhdCI6MTczODI5NDM5NCwiZXhwIjoyMDUzNjU0Mzk0fQ.Rik_K7Bk4hm2YJgORVmFNW1g49xipJEGoFAgT72_qCA"  # Generate from HA


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    
    print("Connecting to WiFi", end="")
    while not wlan.isconnected():
        print(".", end="")
        time.sleep(1)
    print("\n Connected to WiFi:", wlan.ifconfig())


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
    message_id += 1

def led_blink(blinks, delay, pause):
    for _ in range(blinks):
        led.value(1)
        time.sleep(delay)
        led.value(0)
        time.sleep(delay)
    time.sleep(pause)


connect_wifi()
ws = connect_ha_websocket()

if ws:
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
                
#         send_data(ws, "switch.meta_4ch_touch_4", "ON")  # Turn on a light
#         time.sleep(1)
#         send_data(ws, "switch.meta_4ch_touch_4", "OFF")  # Turn off light
#         time.sleep(1)