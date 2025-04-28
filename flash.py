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
CONFIG_PORT = cfg.get('port')

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

        # Top frame for config
        config_frame = tk.Frame(root, bg='#222')
        config_frame.pack(fill='x', pady=5)
        tk.Label(config_frame, text='Port:', font=('Arial', 16), fg='white', bg='#222').pack(side='left', padx=(10,0))
        # Port selection
        self.available_ports = list_ports()
        self.port_var = tk.StringVar(value=CONFIG_PORT if CONFIG_PORT in self.available_ports else (self.available_ports[-1] if self.available_ports else ''))
        self.port_menu = tk.OptionMenu(config_frame, self.port_var, *self.available_ports, command=self.on_port_change)
        self.port_menu.config(font=('Arial', 16), bg='#444', fg='white')
        self.port_menu.pack(side='left', padx=5)

        # Button frame
        btn_frame = tk.Frame(root, bg='#222')
        btn_frame.pack(fill='x', pady=5)
        self.flash_button = tk.Button(btn_frame, text='Flash', font=('Arial', 20),
                                      bg='grey', fg='white', width=10,
                                      command=self.start_flash, state='disabled')
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

        # Initialize
        self.flash_count = self.load_count()
        self.initialize_comm()

    def on_port_change(self, new_port):
        # Called when user selects a different port
        update_config('port', new_port)
        self.log(f"Port manually set to: {new_port}")
        self.initialize_comm()

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

    def initialize_comm(self):
        # refresh available ports
        self.available_ports = list_ports()
        menu = self.port_menu['menu']
        menu.delete(0, 'end')
        for p in self.available_ports:
            menu.add_command(label=p, command=lambda v=p: self.port_var.set(v))
        # ensure port_var is valid
        selected = self.port_var.get()
        if selected not in self.available_ports:
            if self.available_ports:
                selected = self.available_ports[-1]
                self.port_var.set(selected)
                update_config('port', selected)
                self.log(f"Port '{CONFIG_PORT}' unavailable. Auto-set to {selected}.")
        self.PORT = selected if selected else None
        if not self.PORT:
            self.log("Error: No serial ports detected!")
            self.flash_button.config(state='disabled', bg='grey')
            return

        update_config('port', self.PORT)
        # probe at configured baud
        if self.probe_esp(BAUD):
            self.log(f"Comm OK at baud {BAUD}")
            self.flash_button.config(state='normal', bg='green')
        else:
            fallback = '115200'
            self.log(f"Probe failed at baud {BAUD}. Retrying at {fallback}...")
            if self.probe_esp(fallback):
                self.log(f"Comm OK at fallback baud {fallback}")
                update_config('baud', int(fallback))
                self.flash_button.config(state='normal', bg='green')
            else:
                self.log("Error: Cannot communicate with ESP32 on any baud.")
                self.flash_button.config(state='disabled', bg='grey')

    def probe_esp(self, baud):
        self.log(f"Probing ESP32 on {self.PORT} at {baud} baud...")
        try:
            output = subprocess.check_output([
                'python3', '-m', 'esptool',
                '--chip', 'esp32',
                '--port', self.PORT,
                '--baud', baud,
                'chip_id'
            ], stderr=subprocess.STDOUT, text=True, timeout=5)
            self.log(output.strip())
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"Comm error: {e.output.strip()}")
        except subprocess.TimeoutExpired:
            self.log("Comm error: timeout")
        except Exception as e:
            self.log(f"Comm error: {e}")
        return False

    def start_flash(self):
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
        self.initialize_comm()
        self.log('UI reset. Ready.')

if __name__ == '__main__':
    root = tk.Tk()
    app = FlashApp(root)
    root.mainloop()
