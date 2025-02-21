from machine import UART, Pin
import time

# Initialize UART (TX=17, RX=16)
gps_uart = UART(0, baudrate=9600, tx=1, rx=3, timeout=1000)

def read_gps():
    while True:
        if gps_uart.any():
            gps_data = gps_uart.readline()
            if gps_data:
                gps_string = gps_data.decode('utf-8', errors='ignore')
                print(gps_string)  # Print raw NMEA sentences
        time.sleep(1)

# Start reading GPS data
read_gps()

