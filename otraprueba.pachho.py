import threading
import time
import sys
import cv2
import numpy as np
import platform
import os
from datetime import datetime
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None
import tkinter as tk
from tkinter import ttk, messagebox


class CameraSwitcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Cámara múltiple con captura de fotos')
        self.geometry('700x600')

        self.devices = []
        self.max_test_devices = 4

        self.current_cap = None
        self.current_device = None
        self.running = False
        self.scanning = False

        self._build_ui()
        threading.Thread(target=self.enumerate_cameras, daemon=True).start()

        # Carpeta de destino: Imágenes del usuario
        self.capture_folder = os.path.join(os.path.expanduser("~"), "Pictures", "capturas")
        os.makedirs(self.capture_folder, exist_ok=True)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x', padx=10, pady=8)

        ttk.Label(top, text='Cámara:').pack(side='left')
        self.device_var = tk.StringVar()
        self.device_cb = ttk.Combobox(top, textvariable=self.device_var, state='readonly', width=30)
        self.device_cb.pack(side='left', padx=6)

        self.start_btn = ttk.Button(top, text='Iniciar', command=self.start_stream)
        self.start_btn.pack(side='left', padx=4)
        self.stop_btn = ttk.Button(top, text='Detener', command=self.stop_stream)
        self.stop_btn.pack(side='left', padx=4)
        self.next_btn = ttk.Button(top, text='Siguiente cámara', command=self.switch_next)
        self.next_btn.pack(side='left', padx=4)

        self.capture_btn = ttk.Button(top, text='Capturar foto', command=self.capture_photo)
        self.capture_btn.pack(side='left', padx=4)

        mainframe = ttk.Frame(self)
        mainframe.pack(fill='both', expand=True, padx=10, pady=4)
        self.video_panel = ttk.Label(mainframe)
        self.video_panel.pack(fill='both', expand=True)

        self.status_var = tk.StringVar(value='Estado: esperando')
        ttk.Label(self, textvariable=self.status_var).pack(anchor='w', padx=12)

    def log(self, msg):
        self.status_var.set('Estado: ' + msg)

    def enumerate_cameras(self):
        if self.scanning:
            return
        self.scanning = True
        found = []
        self.log('Buscando cámaras...')
        backend = cv2.CAP_DSHOW if platform.system().lower().startswith('win') else 0

        for i in range(self.max_test_devices):
            if not self.scanning:
                break
            try:
                self.after(0, lambda i=i: self.log(f'Escaneando cámara {i+1}/{self.max_test_devices}...'))
                cap = cv2.VideoCapture(i, backend) if backend != 0 else cv2.VideoCapture(i)
                if not cap or not cap.isOpened():
                    if cap:
                        cap.release()
                    continue
                start = time.time()
                while time.time() - start < 0.5:
                    ret, frame = cap.read()
                    if ret:
                        found.append(i)
                        break
                cap.release()
            except Exception as e:
                print(f"Error al probar cámara {i}: {e}")
                continue

        self.scanning = False
        def _ui_update():
            if not found:
                self.device_cb['values'] = []
                self.log('No se encontraron cámaras')
                return
            self.devices = found
            vals = [f'Cámara {d}' for d in self.devices]
            self.device_cb['values'] = vals
            self.device_cb.current(0)
            self.log(f'{len(self.devices)} cámara(s) detectada(s)')
        self.after(0, _ui_update)

    def start_stream(self):
        if Image is None or ImageTk is None:
            messagebox.showerror('Dependencia', 'Instala Pillow: pip install pillow')
            return
        sel = self.device_cb.current()
        if sel < 0 or sel >= len(self.devices):
            messagebox.showwarning('Selecciona', 'Selecciona una cámara antes de iniciar')
            return
        device = self.devices[sel]
        self.open_capture(device)

    def open_capture(self, device):
        self.stop_stream()
        is_win = platform.system().lower().startswith('win')
        backends = [cv2.CAP_MSMF, cv2.CAP_DSHOW, 0] if is_win else [0]

        def backend_name(b):
            if b == cv2.CAP_DSHOW:
                return 'DirectShow'
            if b == cv2.CAP_MSMF:
                return 'MSMF'
            return 'Default'

        last_err = None
        cap = None
        for b in backends:
            try:
                name = backend_name(b)
                self.log(f'Intentando abrir cámara {device} con backend {name}...')
                cap = cv2.VideoCapture(device, b) if b != 0 else cv2.VideoCapture(device)
                if not cap or not cap.isOpened():
                    last_err = f'backend {name} no abrió'
                    if cap:
                        cap.release()
                    cap = None
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                ret, frame = cap.read()
                if not ret or frame is None:
                    last_err = f'backend {name} no devolvió frames'
                    cap.release()
                    cap = None
                    continue
                self.current_cap = cap
                self.current_device = device
                self.running = True
                self.log(f'Transmisión activa (Cámara {device}) - {name}')
                self._update_frame()
                return
            except Exception as e:
                last_err = str(e)
                if cap:
                    cap.release()
                cap = None

        self.log('No se pudo abrir la cámara: ' + (last_err or 'desconocido'))
        messagebox.showerror('Cámara', 'No se pudo abrir la cámara. Cierra otras apps que usen la cámara y revisa permisos.')

    def stop_stream(self):
        self.running = False
        if self.current_cap:
            self.current_cap.release()
            self.current_cap = None
            self.current_device = None
            self.video_panel.config(image='')
            self.log('Transmisión detenida')

    def _update_frame(self):
        if not self.running or not self.current_cap:
            return
        ret, frame = self.current_cap.read()
        if not ret:
            self.log(f'Error: No se pudo leer frame de la cámara {self.current_device}')
            self.after(30, self._update_frame)
            return
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]
        max_w, max_h = 640, 480
        scale = min(max_w / w, max_h / h, 1.0)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_panel.imgtk = imgtk
        self.video_panel.configure(image=imgtk)
        self.after(30, self._update_frame)

    def capture_photo(self):
        if not self.running or not self.current_cap:
            messagebox.showwarning('Aviso', 'Inicia la cámara antes de capturar una foto.')
            return
        ret, frame = self.current_cap.read()
        if not ret:
            messagebox.showerror('Error', 'No se pudo capturar la imagen.')
            return
        filename = f"foto_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
        path = os.path.join(self.capture_folder, filename)
        cv2.imwrite(path, frame)
        messagebox.showinfo('Foto guardada', f'Se guardó la foto:\n{path}')
        self.log(f'Foto guardada: {path}')

    def switch_next(self):
        if not self.devices:
            return
        cur = self.device_cb.current()
        idx = 0 if cur < 0 else (cur + 1) % len(self.devices)
        self.device_cb.current(idx) 
        self.open_capture(self.devices[idx])


def main():
    app = CameraSwitcher()
    app.mainloop()


if __name__ == "__main__":
    main()