import pygame
import socket
import time
import cv2
import numpy as np
import urllib.request

# --- CONFIGURACIÓN ---
PI_IP = "172.20.10.208"  # <--- ¡PON AQUÍ LA IP DE TU RASPBERRY PI!
UDP_PORT = 5005
VIDEO_URL = f"http://{PI_IP}:8090/"

# Inicializar Pygame y Joystick
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("¡No se detectó ningún mando! Conecta uno.")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"Mando detectado: {joystick.get_name()}")

# Configurar Socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("Controles:")
print(" - Eje Y (Joystick Izquierdo): Acelerar/Frenar")
print(" - Eje X (Joystick Derecho): Girar")
print(" - Botón 'B' o 'Círculo': Salir")

running = True

# Ventana para el video (usando OpenCV en el cliente para mostrarlo)
cap = cv2.VideoCapture(VIDEO_URL)

try:
    while running:
        # 1. Procesar eventos de Pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.JOYBUTTONDOWN:
                if event.button == 1: # Botón B/Círculo suele ser 1
                    running = False

        # 2. Leer Joystick (Valores suelen ser -1.0 a 1.0)
        # Nota: Los ejes pueden variar según el mando. 
        # Normalmente eje 1 es Y (invertido) y eje 2 o 3 es X.
        
        throttle = -joystick.get_axis(1) # Invertimos Y porque arriba suele ser negativo
        steering = joystick.get_axis(2)  # Eje X derecho (o 0 para el izquierdo)

        # Zona muerta (para que no se mueva solo)
        if abs(throttle) < 0.1: throttle = 0
        if abs(steering) < 0.1: steering = 0

        # 3. Mezcla "Arcade" (Calcular motor Izq y Der)
        # Velocidad máxima 127 (límite del MD22 Modo 1)
        max_speed = 127
        
        left_motor = (throttle + steering) * max_speed
        right_motor = (throttle - steering) * max_speed

        # Limitar valores a -127 / 127
        left_motor = max(-127, min(127, left_motor))
        right_motor = max(-127, min(127, right_motor))

        # 4. Enviar a Raspberry Pi vía UDP
        msg = f"{int(left_motor)},{int(right_motor)}"
        sock.sendto(msg.encode('utf-8'), (PI_IP, UDP_PORT))

        # 5. Mostrar Video
        ret, frame = cap.read()
        if ret:
            cv2.imshow("Vista del Coche (Q para salir)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                running = False
        
        # Pequeña pausa para no saturar la red (20ms = 50 comandos/segundo)
        time.sleep(0.02)

except KeyboardInterrupt:
    pass

finally:
    # Parar motores al salir
    sock.sendto("0,0".encode('utf-8'), (PI_IP, UDP_PORT))
    cap.release()
    cv2.destroyAllWindows()
    pygame.quit()
    print("Desconectado.")