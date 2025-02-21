import esp32
import sys
import usocket as socket
import ujson
import network
import time
import ubinascii
import urandom

# Home Assistant WebSocket API
HA_HOST = "homeassistant.local"  
HA_PORT = 8123
HA_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2Mjc4YjllOTY2NTA0ZTk3YmVkOTAxY2UwN2YzYjc5YSIsImlhdCI6MTczODI5NDM5NCwiZXhwIjoyMDUzNjU0Mzk0fQ.Rik_K7Bk4hm2YJgORVmFNW1g49xipJEGoFAgT72_qCA"

nvs = esp32.NVS("storage") 

def delete_product_id():
    """Deletes the stored Product ID from NVS."""
    try:
        nvs.erase_key("product_id")
        nvs.commit()
        print("Product ID deleted successfully!")
    except Exception as e:
        print("Error deleting Product ID:", str(e))

# Function to check and update Product ID
def manage_product_id():
    global PRODUCT_ID  # Declare as global to use later
    try:
        stored_product_id = nvs.get_blob("product_id")
        stored_product_id = stored_product_id.decode()  
        print(f"Stored Product ID: {stored_product_id}")
        
        user_input = input("Do you want to delete the stored Product ID? (y/n): ")
        if user_input.lower() == 'y':
            delete_product_id()
            stored_product_id = None
        
    except Exception:
        stored_product_id = None
    
    if stored_product_id is None:
        new_product_id = input("Enter new Product ID: ")
        nvs.set_blob("product_id", new_product_id.encode()) 
        nvs.commit()
        print(f"Stored new Product ID: {new_product_id}")
        PRODUCT_ID = new_product_id  # Assign the new Product ID
    else:
        PRODUCT_ID = stored_product_id  # Use the existing Product ID


manage_product_id()

# Step 2: Initialize WiFi and Configure AP Mode
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
ap = network.WLAN(network.AP_IF) 
ap.active(True)
ap.config(essid=f"onwords-{PRODUCT_ID}", authmode=network.AUTH_OPEN)  # Now PRODUCT_ID is defined

while ap.active() is False:
    time.sleep(1)
print("AP Mode Active. IP Address:", ap.ifconfig()[0])

def store_wifi_credentials(ssid, password):
    """Stores WiFi credentials received from HTTP client."""
    nvs.set_blob("wifi_ssid", ssid.encode())
    nvs.set_blob("wifi_password", password.encode())
    nvs.commit()
    print("WiFi credentials stored successfully.")

def get_stored_wifi_credentials():
    """Retrieves WiFi credentials from NVS."""
    try:
        ssid_buf = bytearray(32)
        pass_buf = bytearray(32)

        if nvs.get_blob("wifi_ssid", ssid_buf) and nvs.get_blob("wifi_password", pass_buf):
            stored_ssid = ssid_buf.decode().strip("\x00")
            stored_password = pass_buf.decode().strip("\x00")
            return stored_ssid, stored_password
    except:
        pass

    return None, None

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

def connect_wifi(ssid, password):
    """Connects to the WiFi network."""
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    wifi.connect(ssid, password)

    for _ in range(10):  # Wait for connection (10 attempts)
        if wifi.isconnected():
            print("Connected to WiFi:", ssid)
            print("IP Address:", wifi.ifconfig()[0])
            return True
    print("WiFi connection failed!")
    return False

def start_http_server():
    """Starts an HTTP server to receive WiFi credentials."""
    addr = ("0.0.0.0", 8182)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Reuse port
    s.bind(addr)
    s.listen(5)
    print("HTTP Server started on 192.168.4.1")
    
    while True:
        conn, addr = s.accept()  # Accept incoming connections and get the connection object
        print(f"Connection established with {addr}")
        handle_request(conn)  # Pass the connection object to handle the request

def handle_request(conn):
    try:
        request = conn.recv(1024).decode()  # Receive the request
        print("Received Request:\n", request)  # Debugging line
        
        if "POST /" in request:  # Check if request is to store WiFi credentials
            try:
                json_data = request.split("\r\n\r\n")[1]  # Extract JSON body
                print("JSON Data Received:", json_data)
                wifi_data = ujson.loads(json_data)  # Parse JSON
                
                ssid = wifi_data.get("SSID", "").strip()
                password = wifi_data.get("PASSWORD", "").strip()
                
                print(f"Received SSID: {ssid}, Password: {password}")
                
                # Store in NVS
                nvs.set_blob("wifi_ssid", ssid.encode())
                nvs.set_blob("wifi_password", password.encode())
                nvs.commit()
                print("WiFi credentials stored successfully!")
                
                response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\": \"success\"}"
                conn.send(response.encode())  # Send response to client
            except Exception as e:
                print("JSON Parsing Error:", e)
                conn.send(b"HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\n\r\n{\"error\": \"Invalid JSON\"}")
    except Exception as e:
        print("Request Handling Error:", e)
    finally:
        conn.close()

stored_ssid, stored_password = get_stored_wifi_credentials()


if stored_ssid and stored_password:
    print("Attempting to connect to stored WiFi credentials...")
    if connect_wifi(stored_ssid, stored_password):
        print("WiFi Connected.")
    else:
        print("Failed to connect to WiFi. Restarting in AP mode.")
        start_http_server()
else:
    print("No WiFi credentials found. Running in AP mode.")
    start_http_server()
