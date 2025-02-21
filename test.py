from machine import Pin
import time

led = Pin(2, Pin.OUT)  # GPIO2 as output

while True:
    led.value(1)  # Turn LED ON
    time.sleep(2)  # Wait 1 second
    led.value(0)  # Turn LED OFF
    time.sleep(2)  # Wait 1 second