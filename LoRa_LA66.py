from machine import UART, Pin
import time

# Initialize UART2 for LA66 communication (Use TX=17, RX=16)
lora_uart = UART(2, baudrate=115200, tx=17, rx=16, timeout=1000)

# Function to send AT command and read response
def send_at_command(command, delay=1):
    lora_uart.write(command + "\r\n")  # Send command with CR+LF
    time.sleep(delay)
    
    if lora_uart.any():  # Check if there is a response
        response = lora_uart.read()
        if response:  # Ensure response is not None
            response = response.decode('utf-8', errors='ignore')
            print("Response:", response)
            return response
    print("No response received.")
    return ""

# Test LA66 module
print("Checking LA66 LoRaWAN module...")
response = send_at_command("AT+CFG")
if "OK" in response:
    print("LA66 is ready!")
else:
    print("No response from LA66! Check connections.")
