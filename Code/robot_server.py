import cv2
import socket
import threading
import time
from flask import Flask, Response

# Variable para saber qué driver estamos usando
ACTIVE_DRIVER = None 
# Objetos para el L298N (se iniciarán solo si falla el I2C)
l298n_left = None
l298n_right = None
bus = None

# --- INTENTO DE CONFIGURACIÓN I2C MD22 ---
MD22_ADDR = 0x58
BUS_NUM = 1
REG_MODE = 0
REG_SPEED_L = 1 
REG_SPEED_R = 2 
REG_ACCEL = 3

print("--- INICIALIZANDO HARDWARE ---")

try:
    import smbus
    bus = smbus.SMBus(BUS_NUM)
    # Intentamos escribir en el MD22 para ver si responde
    bus.write_byte_data(MD22_ADDR, REG_MODE, 1)
    bus.write_byte_data(MD22_ADDR, REG_ACCEL, 0)
    
    ACTIVE_DRIVER = "MD22"
    print("✅ ÉXITO: Driver MD22 (I2C) detectado y activo.")

except Exception as e:
    print(f"⚠️ AVISO: Fallo I2C o MD22 no encontrado ({e}).")
    print("🔄 CAMBIANDO A MODO DE RESPALDO: L298N (GPIO)")
    
    try:
        from gpiozero import Motor
        # CONFIGURACIÓN DE PINES L298N (GPIO BCM)
        # Ajusta estos pines según tu conexión física
        # IN1=17, IN2=27 (Motor A - Izquierda)
        # IN3=22, IN4=23 (Motor B - Derecha)
        l298n_left = Motor(forward=17, backward=27)
        l298n_right = Motor(forward=22, backward=23)
        
        ACTIVE_DRIVER = "L298N"
        print("✅ ÉXITO: Driver L298N inicializado en pines GPIO 17,27 y 22,23.")
    except Exception as gpio_e:
        print(f"❌ ERROR CRÍTICO: No se pudo iniciar ni MD22 ni L298N. {gpio_e}")
        ACTIVE_DRIVER = "NONE"

# --- CONFIGURACIÓN DE RED (UDP) ---
UDP_IP = "0.0.0.0" 
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

last_packet_time = time.time()

# --- FLASK (VIDEO) ---
app = Flask(__name__)
# Intentar abrir cámara, manejando error si no hay cámara
try:
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
except:
    print("⚠️ No se detectó cámara USB")
    camera = None

def set_motors(left, right):
    """ 
    Mueve los motores abstrayendo el hardware.
    Entrada esperada: -128 a 127 
    """
    # 1. Asegurar límites numéricos generales
    left = int(max(-128, min(127, left)))
    right = int(max(-128, min(127, right)))

    if ACTIVE_DRIVER == "MD22":
        try:
            bus.write_byte_data(MD22_ADDR, REG_SPEED_L, left)
            bus.write_byte_data(MD22_ADDR, REG_SPEED_R, right)
        except IOError:
            print("Error I2C durante operación (¿Cable suelto?)")

    elif ACTIVE_DRIVER == "L298N":
        # Conversión: MD22 usa -128/127, L298N(gpiozero) usa -1.0/1.0
        # Dividimos por 128.0 para normalizar
        val_l = left / 128.0
        val_r = right / 128.0
        
        # Asignar valor (gpiozero maneja la dirección automáticamente según el signo)
        l298n_left.value = val_l
        l298n_right.value = val_r

def udp_listener():
    global last_packet_time
    print(f"Escuchando controles UDP en puerto {UDP_PORT}...")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = data.decode('utf-8')
            
            if "," in message:
                parts = message.split(',')
                l_speed = int(parts[0])
                r_speed = int(parts[1])
                
                set_motors(l_speed, r_speed)
                last_packet_time = time.time()
                
        except Exception as e:
            print(f"Error UDP: {e}")

def safety_watchdog():
    """ Parada de emergencia si se pierde señal """
    while True:
        if time.time() - last_packet_time > 0.5:
            # Enviamos 0 para detener, funciona en ambos drivers
            set_motors(0, 0)
        time.sleep(0.1)

def generate_frames():
    if camera is None:
        return # Si no hay cámara, no hacemos nada

    FPS_LIMITE = 30
    CALIDAD_JPEG = 100
    ANCHO_FORZADO = 1280
    ALTO_FORZADO = 720

    while True:
        try:
            success, frame = camera.read()
            if not success:
                break
            
            # Redimensionar (dentro de try por si frame viene vacío)
            frame = cv2.resize(frame, (ANCHO_FORZADO, ALTO_FORZADO))
            
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD_JPEG]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            frame_bytes = buffer.tobytes()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            time.sleep(1 / FPS_LIMITE)
        except Exception as e:
            time.sleep(0.1)

@app.route('/')
def index():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Hilos
    t_udp = threading.Thread(target=udp_listener)
    t_udp.daemon = True
    t_udp.start()

    t_safe = threading.Thread(target=safety_watchdog)
    t_safe.daemon = True
    t_safe.start()

    # Servidor Web
    app.run(host='0.0.0.0', port=8090, debug=False, threaded=True)