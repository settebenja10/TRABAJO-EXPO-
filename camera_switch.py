"""
camera_switch.py - Versión simplificada

Demo en Python que permite:
- Enumerar cámaras conectadas
- Mostrar vídeo de la cámara seleccionada
- Botones: Iniciar, Detener, Siguiente
- Interfaz ligera sin previsualizaciones

Dependencias:
pip install opencv-python pillow

Uso:
python camera_switch.py

Nota: En Windows usa DirectShow para mejor compatibilidad
"""

import threading
import time
import sys
import cv2
import numpy as np
import platform
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
        self.title('Camera Switch - Python')
        self.geometry('640x520')

        self.devices = []  # list of device indices
        self.max_test_devices = 4  # reduce scanning time

        self.current_cap = None
        self.current_device = None
        self.running = False
        self.scanning = False
        self._last_dark_warn = 0
        # lock to protect access to current_cap/current_device when switching
        self.cap_lock = threading.Lock()
        # flag to avoid re-entrant opens
        self.opening = False
        # consecutive read failure counter
        self._fail_count = 0

        self._build_ui()
        # enumerate in background
        threading.Thread(target=self.enumerate_cameras, daemon=True).start()

    def _build_ui(self):
        # controls at top
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
        self.next_btn = ttk.Button(top, text='Siguiente', command=self.switch_next)
        self.next_btn.pack(side='left', padx=4)

        # main video area (single camera view)
        mainframe = ttk.Frame(self)
        mainframe.pack(fill='both', expand=True, padx=10, pady=4)
        self.video_panel = ttk.Label(mainframe)
        self.video_panel.pack(fill='both', expand=True)

        # status at bottom
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
            if not self.scanning:  # allow cancel
                break
            try:
                # update progress
                self.after(0, lambda i=i: self.log(f'Escaneando cámara {i+1}/{self.max_test_devices}...'))
                
                cap = cv2.VideoCapture(i, backend) if backend != 0 else cv2.VideoCapture(i)
                if not cap or not cap.isOpened():
                    if cap:
                        cap.release()
                    continue

                # quick check with timeout
                start = time.time()
                while time.time() - start < 0.5:  # 500ms timeout
                    ret, frame = cap.read()
                    if ret:
                        found.append(i)
                        break
                cap.release()
            except Exception as e:
                print(f"Error al probar cámara {i}: {e}")
                continue

        self.scanning = False
        # update UI on main thread
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
        # perform the heavy open operation in a background thread to avoid blocking the UI
        if self.opening:
            self.log('Apertura en curso, espera...')
            return
        self.opening = True
        threading.Thread(target=self._open_capture_worker, args=(device,), daemon=True).start()

    def _open_capture_worker(self, device):
        # worker runs off the main thread
        try:
            # ensure previous stream is stopped first (safe to call from worker)
            try:
                self.stop_stream()
            except Exception:
                pass

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
                    # update status on main thread
                    self.after(0, lambda n=name, d=device: self.log(f'Intentando abrir cámara {d} con backend {n}...'))
                    cap = cv2.VideoCapture(device, b) if b != 0 else cv2.VideoCapture(device)
                    if not cap or not cap.isOpened():
                        last_err = f'backend {name} no abrió'
                        try:
                            if cap:
                                cap.release()
                        except Exception:
                            pass
                        cap = None
                        continue

                    try:
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    except Exception:
                        pass

                    ret, frame = cap.read()
                    if not ret or frame is None:
                        last_err = f'backend {name} no devolvió frames'
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                        continue

                    # success: install under lock
                    with self.cap_lock:
                        self.current_cap = cap
                        self.current_device = device
                        self._fail_count = 0
                        self.running = True
                    # notify and start frame loop on main thread
                    self.after(0, lambda d=device, n=name: self.log(f'Transmisión activa (Cámara {d}) - {n}'))
                    self.after(0, self._update_frame)
                    return
                except Exception as e:
                    last_err = str(e)
                    try:
                        if cap:
                            cap.release()
                    except Exception:
                        pass
                    cap = None

            # all backends failed
            self.after(0, lambda: self.log('No se pudo abrir la cámara: ' + (last_err or 'desconocido')))
            try:
                self.after(0, lambda: messagebox.showerror('Cámara', 'No se pudo abrir la cámara. Cierra otras apps que usen la cámara y revisa permisos.'))
            except Exception:
                pass
        finally:
            self.opening = False

    def stop_stream(self):
        # stop frame loop and release capture safely
        self.running = False
        with self.cap_lock:
            if self.current_cap:
                try:
                    if self.current_cap.isOpened():
                        self.current_cap.release()
                except Exception:
                    pass
                self.current_cap = None
                self.current_device = None
        try:
            self.video_panel.config(image='')
        except Exception:
            pass
        self.log('Transmisión detenida')

    def _update_frame(self):
        # read a frame from the currently installed capture (thread-safe)
        with self.cap_lock:
            local_cap = self.current_cap
            local_device = self.current_device
        if not self.running or not local_cap:
            return
        try:
            ret, frame = local_cap.read()
            if not ret or frame is None:
                self._fail_count += 1
                self.log(f'Aviso: fallo lectura ({self._fail_count}) de cámara {local_device}')
                if self._fail_count > 10:
                    self.log('Demasiados fallos leyendo frames — reiniciando captura')
                    # try to recover by stopping stream
                    self.stop_stream()
                    return
                # schedule next attempt
                self.after(50, self._update_frame)
                return
            # reset failure counter on success
            self._fail_count = 0
        except Exception as e:
            self.log(f'Error leyendo frame: {e}')
            try:
                self.stop_stream()
            except Exception:
                pass
            return
        # Convert BGR -> RGB
        try:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            self.log('Frame inválido para conversión de color')
            self.after(50, self._update_frame)
            return
        # Resize to fit panel if necessary
        h, w = frame.shape[:2]
        max_w = 640
        max_h = 480
        scale = min(max_w/w, max_h/h, 1.0)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w*scale), int(h*scale)))
        img = Image.fromarray(frame)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_panel.imgtk = imgtk
        self.video_panel.configure(image=imgtk)
        # schedule next
        self.after(30, self._update_frame)

    def switch_next(self):
        if not self.devices:
            return
        cur = self.device_cb.current()
        if cur < 0:
            idx = 0
        else:
            idx = (cur + 1) % len(self.devices)
        self.device_cb.current(idx)
        self.open_capture(self.devices[idx])




def main():
    app = CameraSwitcher()
    app.mainloop()


if __name__ == '__main__':
    main()
