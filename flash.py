#!/usr/bin/env python3
import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import glob
import os
import json
import re

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
        root.update_idletasks()
        w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+0+0")
        root.deiconify()

        # Top frame for controls
        btn_frame = tk.Frame(root, bg='#222')
        btn_frame.pack(fill='x', pady=(0,10))

        # Cycle Port button\        self.port_list = list_ports()
        if CONFIG_PORT in self.port_list:
            self.port_index = self.port_list.index(CONFIG_PORT)
        else:
            self.port_index = len(self.port_list) - 1 if self.port_list else 0
        self.PORT = self.port_list[self.port_index] if self.port_list else None
        self.cycle_button = tk.Button(
            btn_frame, text=f"Port: {self.PORT or 'None'}", font=('Arial', 16),
            bg='blue', fg='white', width=16, height=2, command=self.cycle_port
        )
        self.cycle_button.pack(side='left', padx=10, pady=10)

        # Flash button
        self.flash_button = tk.Button(
            btn_frame, text='Flash', font=('Arial', 20), bg='grey', fg='white',
            width=10, height=2, command=self.start_flash, state='disabled'
        )
        self.flash_button.pack(side='left', padx=10, pady=10)

        # Reset button
        self.reset_button = tk.Button(
            btn_frame, text='Reset', font=('Arial', 20), bg='orange', fg='white',
            width=10, height=2, command=self.reset_ui
        )
        self.reset_button.pack(side='left', padx=10, pady=10)

        # Close button
        self.close_button = tk.Button(
            btn_frame, text='Close', font=('Arial', 20), bg='red', fg='white',
            width=10, height=2, command=root.quit
        )
        self.close_button.pack(side='right', padx=10, pady=10)

        # Progress bar label
        self.progress_var = tk.StringVar(value='')
        self.progress_label = tk.Label(
            root, textvariable=self.progress_var,
            font=('Courier', 18), bg='#111', fg='#0f0'
        )
        self.progress_label.pack(fill='x', padx=10)

        # Log area
        self.log_area = scrolledtext.ScrolledText(
            root, state='disabled', font=('Courier', 14),
            bg='#111', fg='#0f0', wrap='word'
        )
        self.log_area.pack(expand=True, fill='both', padx=10, pady=(0,10))

        # Initialize state
        self.flash_count = self.load_count()
        self.initialize_comm()

    def cycle_port(self):
        self.port_list = list_ports()
        if not self.port_list:
            self.log("No ports to cycle through.")
            return
        self.port_index = (self.port_index + 1) % len(self.port_list)
        self.PORT = self.port_list[self.port_index]
        update_config('port', self.PORT)
        self.cycle_button.config(text=f"Port: {self.PORT}")
        self.log(f"Port switched to: {self.PORT}")
        self.initialize_comm()

    def load_count(self):
        try:
            with open(COUNT_FILE, 'r') as f:
                return int(f.read().strip())
        except:
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
        if not self.PORT:
            self.log("Error: No serial ports detected!")
            self.flash_button.config(state='disabled', bg='grey')
            return
        self.cycle_button.config(text=f"Port: {self.PORT}")
        if self.probe_esp(BAUD):
            self.log(f"Comm OK at baud {BAUD}")
            self.flash_button.config(state='normal', bg='green')
        else:
            fallback = '115200'
            self.log(f"Probe failed at {BAUD}, retrying at {fallback}...")
            if self.probe_esp(fallback):
                update_config('baud', int(fallback))
                self.log(f"Comm OK at fallback baud {fallback}")
                self.flash_button.config(state='normal', bg='green')
            else:
                self.log("Error: Cannot communicate with ESP32 on any baud.")
                self.flash_button.config(state='disabled', bg='grey')

    def probe_esp(self, baud):
        self.log(f"Probing ESP32 on {self.PORT} at {baud} baud...")
        try:
            output = subprocess.check_output([
                'python3', '-m', 'esptool', '--chip', 'esp32',
                '--port', self.PORT, '--baud', baud, 'chip_id'
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
            subprocess.run([
                'python3', '-m', 'esptool', '--chip', 'esp32',
                '--port', self.PORT, '--baud', BAUD, 'erase_flash'
            ], check=True)

            # Write firmware with progress bar update
            self.log('Writing firmware...')
            cmd = [
                'python3', '-m', 'esptool', '--chip', 'esp32',
                '--port', self.PORT, '--baud', BAUD,
                'write_flash', '-z', '0x0', BIN
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                m = re.search(r"\(\s*(\d+)%\s*\)", line)
                if m:
                    percent = int(m.group(1))
                    bars = '|' * (percent // 5)  # 20 bars max
                    self.progress_var.set(bars)
            ret = proc.wait()
            if ret != 0:
                raise subprocess.CalledProcessError(ret, cmd)

            self.log('Auto-resetting ESP32...')
            self.reset_esp()
            self.initialize_comm()

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

    def reset_esp(self):
        if not self.PORT:
            self.log("Cannot reset: no port.")
            return
        self.log('Performing hardware reset...')
        try:
            subprocess.run([
                'python3', '-m', 'esptool', '--chip', 'esp32',
                '--port', self.PORT, '--baud', BAUD, 'run'
            ], check=True)
            self.log('Hardware reset successful.')
        except Exception as e:
            self.log(f'Hardware reset failed: {e}')

    def reset_ui(self):
        self.progress_var.set('')
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', 'end')
        self.log_area.config(state='disabled')
        self.initialize_comm()
        self.log('UI reset. Ready.')

if __name__ == '__main__':
    root = tk.Tk()
    app = FlashApp(root)
    root.mainloop()
