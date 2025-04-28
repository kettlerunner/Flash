#!/usr/bin/env python3
import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import glob
import os
import json

# Paths
SCRIPT_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'settings.json')

# Load configuration
try:
    with open(CONFIG_PATH, 'r') as cfg_file:
        cfg = json.load(cfg_file)
except Exception as e:
    print(f"Failed to load config '{CONFIG_PATH}': {e}")
    exit(1)

# Assign settings
BIN = cfg.get('bin')
BAUD = str(cfg.get('baud', 1152000))
COUNT_FILE = cfg.get('count_file')
SUCCESS_WAV = cfg.get('success_wav')
ERROR_WAV = cfg.get('error_wav')
CONFIG_PORT = cfg.get('port')  # may be None

# Helpers
def list_ports():
    return sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))

def update_config(key, value):
    cfg[key] = value
    try:
        with open(CONFIG_PATH, 'w') as cfg_file:
            json.dump(cfg, cfg_file, indent=2)
    except Exception as e:
        print(f"Failed to update config: {e}")

class FlashApp:
    def __init__(self, root):
        self.root = root
        # Fullscreen kiosk
        root.withdraw()
        root.overrideredirect(True)
        root.attributes('-fullscreen', True, '-topmost', True)
        root.config(cursor='none')
        root.update_idletasks()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+0+0")
        root.deiconify()

        # Top frame for buttons
        btn_frame = tk.Frame(root, bg='#222')
        btn_frame.pack(fill='x', pady=5)

        self.flash_button = tk.Button(btn_frame, text='Flash', font=('Arial', 20),
                                      bg='green', fg='white', width=10,
                                      command=self.start_flash)
        self.flash_button.pack(side='left', padx=10)
        self.reset_button = tk.Button(btn_frame, text='Reset', font=('Arial', 20),
                                      bg='orange', fg='white', width=10,
                                      command=self.reset_ui)
        self.reset_button.pack(side='left', padx=10)
        self.close_button = tk.Button(btn_frame, text='Close', font=('Arial', 20),
                                      bg='red', fg='white', width=10,
                                      command=root.quit)
        self.close_button.pack(side='right', padx=10)

        # Log area
        self.log_area = scrolledtext.ScrolledText(root, state='disabled',
                                                  font=('Courier', 14), bg='#111', fg='#0f0', wrap='word')
        self.log_area.pack(expand=True, fill='both', padx=10, pady=(0,10))

        # Determine serial port
        available = list_ports()
        if CONFIG_PORT and CONFIG_PORT in available:
            self.PORT = CONFIG_PORT
            self.log(f"Using configured port: {self.PORT}")
        elif available:
            new_port = available[-1]
            self.PORT = new_port
            self.log(f"Configured port '{CONFIG_PORT}' not found. Using '{new_port}'.")
            update_config('port', new_port)
            self.log(f"Updated settings.json with port: {new_port}")
        else:
            self.PORT = None
            self.log("Error: No serial ports detected!")
            self.flash_button.config(state='disabled', bg='grey')

        # Load flash count
        self.flash_count = self.load_count()

    def load_count(self):
        try:
            with open(COUNT_FILE, 'r') as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def save_count(self):
        try:
            with open(COUNT_FILE, 'w') as f:
                f.write(str(self.flash_count))
        except Exception as e:
            self.log(f"Warning: could not save count: {e}")

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert('end', message + '\n')
        self.log_area.yview('end')
        self.log_area.config(state='disabled')
        print(message)

    def play_sound(self, wav):
        self.root.bell()
        if wav and os.path.exists(wav):
            subprocess.run(['aplay', wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_flash(self):
        if not self.PORT:
            self.log('Cannot flash: no port available')
            return
        self.flash_button.config(state='disabled', bg='yellow')
        self.reset_button.config(state='disabled')
        self.log('Starting flash sequence...')
        threading.Thread(target=self.flash_esp32, daemon=True).start()

    def flash_esp32(self):
        try:
            self.log('Erasing flash...')
            subprocess.run(['python3', '-m', 'esptool',
                             '--chip', 'esp32', '--port', self.PORT,
                             '--baud', BAUD, 'erase_flash'], check=True)
            self.log('Writing firmware...')
            subprocess.run(['python3', '-m', 'esptool',
                             '--chip', 'esp32', '--port', self.PORT,
                             '--baud', BAUD, 'write_flash', '-z', '0x0', BIN], check=True)
            self.log('Resetting ESP32...')
            subprocess.run(['python3', '-m', 'esptool',
                             '--chip', 'esp32', '--port', self.PORT,
                             '--baud', BAUD, 'run'], check=True)

            self.flash_count += 1
            self.save_count()
            self.log(f'✔ Flash complete ({self.flash_count} runs).')
            self.play_sound(SUCCESS_WAV)
            self.flash_button.config(bg='green')

        except subprocess.CalledProcessError as e:
            self.log(f'❌ Flash failed: {e}')
            self.play_sound(ERROR_WAV)
            messagebox.showerror('Error', 'Flash failed. Use Reset to retry.')
            self.flash_button.config(bg='red')
        finally:
            self.reset_button.config(state='normal')

    def reset_ui(self):
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', 'end')
        self.log_area.config(state='disabled')
        self.flash_button.config(state='normal', bg='green')
        self.log('UI reset. Ready.')

if __name__ == '__main__':
    root = tk.Tk()
    app = FlashApp(root)
    root.mainloop()
