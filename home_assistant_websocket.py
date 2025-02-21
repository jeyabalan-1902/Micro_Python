import uwebsocket
import usocket
import ujson
import network
import time


SSID = "Rnd"
PASSWORD = "nikhil8182"

HA_WS_URL = "ws://homeassistant.local:8123/api/websocket"
HA_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2Mjc4YjllOTY2NTA0ZTk3YmVkOTAxY2UwN2YzYjc5YSIsImlhdCI6MTczODI5NDM5NCwiZXhwIjoyMDUzNjU0Mzk0fQ.Rik_K7Bk4hm2YJgORVmFNW1g49xipJEGoFAgT72_qCA"  # Generate from Home Assistant

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    
    print("🔗 Connecting to WiFi", end="")
    while not wlan.isconnected():
        print(".", end="")
        time.sleep(1)
    print("\n✅ Connected to WiFi:", wlan.ifconfig())


def connect_ha_websocket():
    print("🔗 Connecting to Home Assistant WebSocket...")

    # Create a socket connection
    sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
    sock.connect(usocket.getaddrinfo("homeassistant.local", 8123)[0][-1])

    ws = uwebsocket.client(sock) 

    # Send authentication request
    auth_payload = ujson.dumps({"type": "auth", "access_token": HA_AUTH_TOKEN})
    ws.send(auth_payload)

    # Wait for authentication response
    while True:
        message = ws.recv()
        print("📩 Received:", message)

        msg_json = ujson.loads(message)
        if msg_json.get("type") == "auth_ok":
            print("✅ Authentication successful with Home Assistant")
            break
        elif msg_json.get("type") == "auth_invalid":
            print("❌ Authentication failed!")
            return None

    return ws


def send_data(ws, entity_id, state):
    msg = {
        "id": 1,
        "type": "call_service",
        "domain": "homeassistant",
        "service": "turn_on" if state == "ON" else "turn_off",
        "service_data": {"entity_id": entity_id}
    }
    ws.send(ujson.dumps(msg))
    print(f"📤 Sent command: {state} -> {entity_id}")


# Main Execution
connect_wifi()
ws = connect_ha_websocket()

if ws:
    while True:
        send_data(ws, "light.living_room", "ON")  
        time.sleep(5)
        send_data(ws, "light.living_room", "OFF")  
        time.sleep(5)
