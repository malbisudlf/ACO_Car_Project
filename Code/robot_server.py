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

# --- CAMARA (MODIFICADO PARA MÁXIMA RESOLUCIÓN) ---
app = Flask(__name__)
try:
    # Usamos V4L2 explícitamente para la Pi 5
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    
    # Intentamos establecer 1920x1080 (Full HD)
    # Si la cámara no llega a tanto, OpenCV usará la máxima disponible cercana.
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    # Forzamos formato MJPG para que sea más rápido procesar HD
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
    
    # Imprimimos la resolución real conseguida para confirmar
    real_w = camera.get(cv2.CAP_PROP_FRAME_WIDTH)
    real_h = camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
    print(f"📷 Cámara iniciada a: {int(real_w)}x{int(real_h)}")
    
except Exception as e:
    print(f"❌ Error Cámara: {e}")
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
        val_l = left / 128.0
        val_r = right / 128.0 
        if abs(val_l) < 0.2: val_l = 0
        if abs(val_r) < 0.2: val_r = 0
        l298n_left.value = val_l
        l298n_right.value = val_r

def play_jingle():
    global is_playing
    if is_playing or not buzzer: return
    
    is_playing = True
    print("🎄 Reproduciendo Villancico...")
    
    melody = [
        ('G4', 0.2),
        ('C5', 0.4), ('B4', 0.2), ('C5', 0.2), ('A4', 0.8),
        ('G4', 0.2),
        ('D5', 0.4), ('C#5', 0.2), ('D5', 0.2), ('B4', 0.8),
        ('G4', 0.2),
        ('E5', 0.4), ('D5', 0.2), ('C5', 0.2), ('B4', 0.4), ('A4', 0.4),
        ('F5', 0.2), ('F5', 0.2),
        ('E5', 0.2), ('E5', 0.2),
        ('D5', 0.2), ('G4', 0.2), ('C5', 0.8),
    ]

    try:
        for note, duration in melody:
            buzzer.play(Tone(note))
            time.sleep(duration)
        buzzer.stop()
    except: pass
    
    is_playing = False

def udp_listener():
    global last_packet_time
    while True:
        try:
            data, _ = sock.recvfrom(1024)
            msg = data.decode('utf-8')
            if msg == "NAVIDAD":
                threading.Thread(target=play_jingle, daemon=True).start()
                last_packet_time = time.time()
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
            # Voltear imagen (-1 = 180 grados)
            frame = cv2.flip(frame, -1)
            
            # Codificar a JPEG. 
            # Calidad 70 es un buen balance entre HD y velocidad. 
            # Si va lento, baja este 70 a 50.
            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            
            # He reducido el sleep para intentar mantener más FPS con la alta resolución
            time.sleep(0.01) 
        except: pass

@app.route('/')
def index():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    threading.Thread(target=udp_listener, daemon=True).start()
    threading.Thread(target=safety_watchdog, daemon=True).start()
    # Usamos host 0.0.0.0 para que sea accesible desde la red
    app.run(host='0.0.0.0', port=8090, debug=False, threaded=True)  