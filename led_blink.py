from machine import Pin
from utime import sleep

led = Pin(2, Pin.OUT)  # GPIO2 as output

while True:
    led.on()
    print("led is:", led.value())
    sleep(0.5)
    led.off()
    print("led is:", led.value())
    sleep(0.5)
