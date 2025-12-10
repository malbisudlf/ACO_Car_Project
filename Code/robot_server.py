import cv2
import socket
import threading
import time
from flask import Flask, Response
from gpiozero import TonalBuzzer
from gpiozero.tones import Tone

# --- CONFIG BUZZER ---
try:
    buzzer = TonalBuzzer(25)
except Exception as e:
    print(f"⚠️ No se pudo iniciar el buzzer: {e}")
    buzzer = None

is_playing = False

# Variable de estado del driver
ACTIVE_DRIVER = None 
l298n_left = None
l298n_right = None
bus = None

# --- CONFIG I2C ---
MD22_ADDR = 0x58
BUS_NUM = 1
try:
    import smbus
    bus = smbus.SMBus(BUS_NUM)
    bus.write_byte_data(MD22_ADDR, 0, 1) # Mode 1
    bus.write_byte_data(MD22_ADDR, 3, 0) # Accel
    ACTIVE_DRIVER = "MD22"
    print("✅ MD22 Activo")
except:
    print("🔄 Usando L298N (Respaldo)")
    try:
        from gpiozero import Motor
        
        # --- CONFIGURACIÓN DE PINES Y DIRECCIÓN ---
        # SI UNA RUEDA GIRA AL REVÉS: Intercambia los números de 'forward' y 'backward'
        # Ejemplo: Si la izq va al revés, pon forward=27, backward=17
        
        l298n_left = Motor(forward=17, backward=27)   # Motor Izquierdo
        l298n_right = Motor(forward=22, backward=23)  # Motor Derecho
        
        ACTIVE_DRIVER = "L298N"
        print("✅ L298N Activo")
    except Exception as e:
        print(f"❌ Error Drivers: {e}")
        ACTIVE_DRIVER = "NONE"

# --- RED ---
UDP_IP = "0.0.0.0" 
UDP_PORT = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

last_packet_time = time.time()

# --- CAMARA ---
app = Flask(__name__)
try:
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
except:
    camera = None

def set_motors(left, right):
    # Asegurar rango -128 a 127
    left = int(max(-128, min(127, left)))
    right = int(max(-128, min(127, right)))

    if ACTIVE_DRIVER == "MD22":
        try:
            bus.write_byte_data(MD22_ADDR, 1, left)
            bus.write_byte_data(MD22_ADDR, 2, right)
        except: pass

    elif ACTIVE_DRIVER == "L298N":
        # Normalizar para gpiozero (-1.0 a 1.0)
        # IMPORTANTE: Si un motor va al revés por software, pon un - delante
        val_l = left / 128.0
        val_r = right / 128.0 
        
        # Zona muerta pequeña para evitar zumbidos
        if abs(val_l) < 0.2: val_l = 0
        if abs(val_r) < 0.2: val_r = 0
        
        l298n_left.value = val_l
        l298n_right.value = val_r

def play_jingle():
    global is_playing
    if is_playing or not buzzer: return # Si ya suena o no hay buzzer, salir
    
    is_playing = True
    print("🎄 Reproduciendo Villancico...")
    
    # Notas: (Nota, Duración)
    melody = [
        # --- Feliz Navidad (1) ---
        ('G4', 0.2), # (Pickup)
        ('C5', 0.4), ('B4', 0.2), ('C5', 0.2), ('A4', 0.8), # Fe-liz Na-vi-dad
        
        # --- Feliz Navidad (2) ---
        ('G4', 0.2), # (Pickup)
        ('D5', 0.4), ('C#5', 0.2), ('D5', 0.2), ('B4', 0.8), # Fe-liz Na-vi-dad
        
        # --- Feliz Navidad (3) ---
        ('G4', 0.2), # (Pickup)
        ('E5', 0.4), ('D5', 0.2), ('C5', 0.2), ('B4', 0.4), ('A4', 0.4), # Fe-liz Na-vi-dad
        
        # --- Próspero año y felicidad ---
        ('F5', 0.2), ('F5', 0.2), # Prós-pe
        ('E5', 0.2), ('E5', 0.2), # ro-a
        ('D5', 0.2), ('G4', 0.2), ('C5', 0.8), # ño-y-fe-li-ci-dad
    ]

    try:
        for note, duration in melody:
            buzzer.play(Tone(note))
            time.sleep(duration)
        buzzer.stop()
    except:
        pass
    
    is_playing = False

def udp_listener():
    global last_packet_time
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            msg = data.decode('utf-8')
            
            # COMANDO DE MÚSICA
            if msg == "NAVIDAD":
                threading.Thread(target=play_jingle, daemon=True).start()
                last_packet_time = time.time() # Mantener vivo el robot
            
            # COMANDO DE MOTORES (Mantiene tu lógica original)
            elif "," in msg:
                l, r = map(int, msg.split(','))
                set_motors(l, r)
                last_packet_time = time.time()
        except: pass
def safety_watchdog():
    while True:
        if time.time() - last_packet_time > 0.5:
            set_motors(0, 0)
        time.sleep(0.1)

def generate_frames():
    if not camera: return
    while True:
        success, frame = camera.read()
        if not success: break
        try:
            # Bajar calidad para velocidad
            frame = cv2.resize(frame, (640, 480))
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.05) # Max 20 FPS
        except: pass

@app.route('/')
def index():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    threading.Thread(target=udp_listener, daemon=True).start()
    threading.Thread(target=safety_watchdog, daemon=True).start()
    app.run(host='0.0.0.0', port=8090, debug=False, threaded=True)