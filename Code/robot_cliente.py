import pygame
import socket
import time
import cv2
import numpy as np

# --- CONFIGURACIÓN ---
PI_IP = "10.235.21.46"  # <--- TU IP
UDP_PORT = 5005
VIDEO_URL = f"http://{PI_IP}:8090/"

# Inicializar Pygame
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

print("--- CONTROLES ---")
print("Si el coche hace cosas raras, ajusta los ejes en el código.")

# Ventana Video
cap = cv2.VideoCapture(VIDEO_URL)
running = True

try:
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.JOYBUTTONDOWN:
                if event.button == 1:
                    running = False

                if event.button == 0:
                    print("🎵 Enviando comando Navidad...")
                    sock.sendto("NAVIDAD".encode('utf-8'), (PI_IP, UDP_PORT))

        # --- CORRECCIÓN DE EJES ---
        # He intercambiado el 2 y el 3 basándome en tu problema.
        # Si tu mando es estándar (Xbox/PS4), a veces los ejes son 0 (izq/der) y 1 (arriba/abajo).
        # Prueba esta configuración primero:
        
        raw_throttle = -joystick.get_axis(3)
        raw_steering = -joystick.get_axis(2)

        # Zona muerta
        throttle = 0 if abs(raw_throttle) < 0.1 else raw_throttle
        steering = 0 if abs(raw_steering) < 0.1 else raw_steering

        # --- MEZCLA ARCADE ---
        max_speed = 127
        
        # Fórmula estándar de mezcla
        left_motor = (throttle + steering) * max_speed
        right_motor = (throttle - steering) * max_speed

        # Limitar y convertir a entero
        left_motor = int(max(-127, min(127, left_motor)))
        right_motor = int(max(-127, min(127, right_motor)))

        # Enviar
        msg = f"{left_motor},{right_motor}"
        sock.sendto(msg.encode('utf-8'), (PI_IP, UDP_PORT))

        # Video
        ret, frame = cap.read()
        if ret:
            cv2.imshow("Coche Robot", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                running = False
        
        time.sleep(0.02)

except KeyboardInterrupt:
    pass

finally:
    sock.sendto("0,0".encode('utf-8'), (PI_IP, UDP_PORT))
    cap.release()
    cv2.destroyAllWindows()
    pygame.quit()