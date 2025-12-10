from gpiozero import Motor
from time import sleep

# Usa los pines que definiste
motor = Motor(forward=17, backward=27)

print("Intentando arrancar al 100% de potencia...")
motor.forward(1.0) # Velocidad máxima absoluta
sleep(3)
motor.stop()