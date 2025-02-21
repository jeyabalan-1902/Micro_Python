import network
import urequests
import uasyncio as asyncio
from mfrc522 import MFRC522
from machine import SPI, Pin

# Wi-Fi Credentials
WIFI_SSID = "Onwords"
WIFI_PASSWORD = "nikhil8182"

# Base API URL (without UID)
API_BASE_URL = "https://api.onwords.in/update_id_card"


# Initialize SPI for RFID
spi = SPI(2, baudrate=2500000, polarity=0, phase=0)
spi.init()

# Setup MFRC522 RFID Reader
rdr = MFRC522(spi=spi, gpioRst=4, gpioCs=5)

led = Pin(15, Pin.OUT)  
led.value(0)

async def blink_led():
    """Blink LED while waiting for Wi-Fi connection."""
    while not network.WLAN(network.STA_IF).isconnected():
        led.value(1)
        await asyncio.sleep(0.5)
        led.value(0)
        await asyncio.sleep(0.5)

async def connect_wifi():
    """Connect ESP32 to Wi-Fi."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    print("Connecting to Wi-Fi...")
    while not wlan.isconnected():
         await blink_led()
    print("Connected to Wi-Fi:", wlan.ifconfig())
    led.value(0)


async def send_to_api(uid):
    """Send RFID UID by appending it to the API URL."""
    formatted_uid = uid.upper().replace("0X", "")  # Convert to uppercase & remove '0x'
    api_url = f"{API_BASE_URL}/{formatted_uid}"  
    
    try:
        print(f"Sending request to: {api_url}")
        response = urequests.post(api_url)
        print("API Response:", response.text)
        response.close()
    except Exception as e:
        print("Failed to send data:", str(e))
    finally:
        led.value(0)


async def scan_rfid():
    """Scan for RFID card and send UID to API."""
    print("Place card...")

    while True:
        (stat, tag_type) = rdr.request(rdr.REQIDL)
        if stat == rdr.OK:
            (stat, raw_uid) = rdr.anticoll()
            if stat == rdr.OK:
                card_id = "0x%02x%02x%02x%02x" % (raw_uid[0], raw_uid[1], raw_uid[2], raw_uid[3])
                print("Card UID:", card_id)
                led.value(1)
                # Send UID to API
                await send_to_api(card_id)

                # Small delay to prevent duplicate readings
                await asyncio.sleep(2)
        await asyncio.sleep(0.1)  # Allow other tasks to run


async def main():
    """Main function to run Wi-Fi and RFID scanning tasks concurrently."""
    await connect_wifi()  
    await asyncio.gather(scan_rfid()) 

# Run the main event loop
asyncio.run(main())
