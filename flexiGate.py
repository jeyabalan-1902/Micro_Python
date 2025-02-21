from micropython import const
import asyncio
import aioble
import bluetooth
import machine
import network
import ubinascii
import umqtt.simple as mqtt

# Wi-Fi Credentials
WIFI_SSID = "Onwords"
WIFI_PASSWORD = "nikhil8182"

# MQTT Broker Details
BROKER_ADDRESS = "mqtt.onwords.in"
MQTT_CLIENT_ID = "test"
PORT = 1883  
USERNAME = "Nikhil"
MQTT_PASSWORD = "Nikhil8182"
MQTT_KEEPALIVE = 60 
MQTT_TOPIC_SUB = "rnd/command"  # MQTT topic to receive data
MQTT_TOPIC_PUB = "rnd/status"  # MQTT topic to publish data

# Init LED
led = machine.Pin(2, machine.Pin.OUT)
led.value(0)

# UART2 Configuration (TX=17, RX=16)
uart2 = machine.UART(2, baudrate=115200, tx=17, rx=16)
uart2.init(115200, bits=8, parity=None, stop=1)

# BLE UUIDs
_BLE_SERVICE_UUID = bluetooth.UUID('19b10000-e8f2-537e-4f6c-d104768a1214')
_BLE_SENSOR_CHAR_UUID = bluetooth.UUID('19b10001-e8f2-537e-4f6c-d104768a1214')
_BLE_LED_UUID = bluetooth.UUID('19b10002-e8f2-537e-4f6c-d104768a1214')

_ADV_INTERVAL_MS = 250_000

# Register GATT service
ble_service = aioble.Service(_BLE_SERVICE_UUID)
led_characteristic = aioble.Characteristic(ble_service, _BLE_LED_UUID, read=True, write=True, notify=True, capture=True)
aioble.register_services(ble_service)

# Connect to Wi-Fi
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    print("Connecting to Wi-Fi...")
    while not wlan.isconnected():
        pass
    
    print("Connected to Wi-Fi:", wlan.ifconfig())

# Connect to MQTT broker
client = mqtt.MQTTClient(MQTT_CLIENT_ID, server=BROKER_ADDRESS, port=PORT, user=USERNAME, password=MQTT_PASSWORD, keepalive=MQTT_KEEPALIVE)

def connect_mqtt():
    try:
        client.connect()
        print("Connected to MQTT broker")
        client.set_callback(mqtt_callback)
        client.subscribe(MQTT_TOPIC_SUB)
    except Exception as e:
        print("MQTT connection error:", e)

def reconnect_mqtt():
    global client
    print("Reconnecting MQTT...")
    try:
        client.disconnect()
    except:
        pass
    client = mqtt.MQTTClient(MQTT_CLIENT_ID, server=BROKER_ADDRESS, port=PORT, user=USERNAME, password=MQTT_PASSWORD, keepalive=MQTT_KEEPALIVE)
    connect_mqtt()

# Handle incoming MQTT messages
def mqtt_callback(topic, msg):
    try:
        print(f"Received from MQTT: {msg}")
        #msg_int = int(msg.decode())
        if msg == b'1' or msg == b'0':
            led.value(not led.value())       
        uart2.write(msg + b'\n')  # Send received data to UART
    except Exception as e:
        print("Error in MQTT callback:", e)

def _encode_data(data):
    return str(data).encode('utf-8')

# Helper to decode the LED characteristic encoding (bytes).
def _decode_data(data):
    try:
        if data is not None:
            # Decode the UTF-8 data
            number = int.from_bytes(data, 'big')
            return number
    except Exception as e:
        print("Error decoding temperature:", e)
        return None

# Handle BLE writes
async def wait_for_write():
    while True:
        try:
            connection, data = await led_characteristic.written()
            print(data)
            print(type)
            data = _decode_data(data)
            print('Connection: ', connection)
            print('Data: ', data)
            if data == 1 or data == 0:
                led.value(not led.value())
                uart2.write(str(data).encode() + b'\n') 
                print("Sent to UART")
            else:
                print('Unknown command')
        except asyncio.CancelledError:
            # Catch the CancelledError
            print("Peripheral task cancelled")
        except Exception as e:
            print("Error in peripheral_task:", e)
        finally:
            # Ensure the loop continues to the next iteration
            await asyncio.sleep_ms(100)

async def mqtt_keepalive():
    while True:
        try:
            print("Sending MQTT PINGREQ")
            client.ping()  # Send PINGREQ to keep connection alive
        except Exception as e:
            print("MQTT Keep-Alive failed:", e)
            reconnect_mqtt()
        await asyncio.sleep(MQTT_KEEPALIVE // 2) 

# Listen for MQTT messages
async def mqtt_listener():
    while True:
        try:
            client.check_msg()
        except Exception as e:
            print("Error checking MQTT:", e)
            reconnect_mqtt()
        await asyncio.sleep(1)

# Start BLE peripheral
async def peripheral_task():
    while True:
        try:
            async with await aioble.advertise(
                _ADV_INTERVAL_MS, name="R&D Ble test", services=[_BLE_SERVICE_UUID]
            ) as connection:
                print("Connected to BLE device:", connection.device)
                await connection.disconnected()
        except asyncio.CancelledError:
            print("Peripheral task cancelled")
        except Exception as e:
            print("Error in peripheral task:", e)
        finally:
            await asyncio.sleep_ms(100)

# Run all tasks
async def main():
    connect_wifi()
    connect_mqtt()
    
    t1 = asyncio.create_task(peripheral_task())
    t2 = asyncio.create_task(wait_for_write())
    t3 = asyncio.create_task(mqtt_listener())
    t4 = asyncio.create_task(mqtt_keepalive()) 

    await asyncio.gather(t1, t2, t3, t4)

asyncio.run(main())

