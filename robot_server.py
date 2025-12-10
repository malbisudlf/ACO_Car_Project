import cv2
import socket
import threading
import smbus
import time
from flask import Flask, Response

# --- CONFIGURACIÓN I2C MD22 ---
# Dirección I2C (0xB0 >> 1 = 0x58 para Raspberry Pi)
MD22_ADDR = 0x58
BUS_NUM = 1
bus = smbus.SMBus(BUS_NUM)

# Registros MD22
REG_MODE = 0
REG_SPEED_L = 1 # Speed1
REG_SPEED_R = 2 # Speed2 (o Turn dependiendo del modo)
REG_ACCEL = 3

# Configurar MD22 en MODO 1 (Control independiente, -128 a 127)
# Esto nos da control total sobre cada oruga/rueda.
try:
    bus.write_byte_data(MD22_ADDR, REG_MODE, 1)
    bus.write_byte_data(MD22_ADDR, REG_ACCEL, 0) # Aceleración máxima
except Exception as e:
    print(f"Error inicializando MD22 (¿Está conectado?): {e}")

# --- CONFIGURACIÓN DE RED (UDP) ---
UDP_IP = "0.0.0.0" # Escuchar en todas las interfaces
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

# Variable de seguridad para detener el coche si se pierde la conexión
last_packet_time = time.time()

# --- FLASK (VIDEO) ---
app = Flask(__name__)
camera = cv2.VideoCapture(0, cv2.CAP_V4L2) # 0 suele ser la primera webcam USB
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320) # Baja resolución para menos lag
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

def set_motors(left, right):
    """ Mueve los motores. Valores de -128 a 127 """
    try:
        # Asegurar límites
        left = int(max(-128, min(127, left)))
        right = int(max(-128, min(127, right)))
        
        bus.write_byte_data(MD22_ADDR, REG_SPEED_L, left)
        bus.write_byte_data(MD22_ADDR, REG_SPEED_R, right)
    except IOError:
        pass # Ignorar errores puntuales de I2C

def udp_listener():
    """ Hilo que escucha comandos del mando """
    global last_packet_time
    print(f"Escuchando controles en el puerto UDP {UDP_PORT}...")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = data.decode('utf-8')
            
            # Formato esperado: "izq,der" (ej: "100,-100")
            if "," in message:
                parts = message.split(',')
                l_speed = int(parts[0])
                r_speed = int(parts[1])
                
                set_motors(l_speed, r_speed)
                last_packet_time = time.time()
                
        except Exception as e:
            print(f"Error UDP: {e}")

def safety_watchdog():
    """ Si no recibimos datos en 0.5 segundos, paramos los motores (Safety) """
    while True:
        if time.time() - last_packet_time > 0.5:
            set_motors(0, 0)
        time.sleep(0.1)

def generate_frames():
    # --- CONFIGURACIÓN DE AHORRO ---
    FPS_LIMITE = 1           # Enviar solo 10 fotos por segundo
    CALIDAD_JPEG = 10        # Calidad 25% (baja mucho el peso, se ve "pixelado" pero fluido)
    ANCHO_FORZADO = 160       # Resolución muy pequeña
    ALTO_FORZADO = 120
    # -------------------------------

    while True:
        success, frame = camera.read()
        if not success:
            break
        
        # 1. Reducir tamaño de la imagen a la fuerza
        try:
            frame = cv2.resize(frame, (ANCHO_FORZADO, ALTO_FORZADO))
        except:
            pass

        # 2. Convertir a Blanco y Negro (Opcional: Descomenta la linea de abajo para ahorrar aun mas)
        # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 3. Compresión agresiva JPEG
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD_JPEG]
        ret, buffer = cv2.imencode('.jpg', frame, encode_param)
        
        frame_bytes = buffer.tobytes()

        # 4. Enviar
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # 5. Esperar un poco para no saturar (Limitador de FPS)
        # Si queremos 10 FPS, esperamos 0.1 segundos entre envío y envío
        time.sleep(1 / FPS_LIMITE)
@app.route('/')
def index():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Iniciar hilos de control en segundo plano
    t_udp = threading.Thread(target=udp_listener)
    t_udp.daemon = True
    t_udp.start()

    t_safe = threading.Thread(target=safety_watchdog)
    t_safe.daemon = True
    t_safe.start()

    # Iniciar servidor web (Video)
    # host='0.0.0.0' hace que sea accesible desde la red
    app.run(host='0.0.0.0', port=8090, debug=False, threaded=True)