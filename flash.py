#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import glob
import os

# Paths and settings
BIN = '/home/pi/FR1_FACTORY.bin'       # Firmware binary
BAUD = '1152000'
COUNT_FILE = '/home/pi/flash_count.txt'
SUCCESS_WAV = '/home/pi/success.wav'
ERROR_WAV = '/home/pi/error.wav'

# Auto-detect ESP32 serial port
def detect_port():
    ports = sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*'))
    return ports[-1] if ports else None

class FlashApp:
    def __init__(self, root):
        self.root = root
        # Borderless fullscreen & hide cursor
        root.overrideredirect(True)
        root.attributes('-fullscreen', True)
        root.config(cursor='none')

        # Screen dimensions
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        # Dynamic font sizes
        btn_size = int(screen_h * 0.2)
        status_size = int(screen_h * 0.05)
        count_size = int(screen_h * 0.04)

        # UI variables
        self.status_text = tk.StringVar(value='Ready to flash.')
        self.flash_count = self.load_count()
        self.count_text = tk.StringVar(value=f'Flashes Completed: {self.flash_count}')

        # FLASH button
        self.flash_button = tk.Button(
            root, text='FLASH', font=('Arial', btn_size),
            bg='green', fg='white', command=self.start_flash
        )
        self.flash_button.pack(expand=True, fill='both', padx=10, pady=10)

        # Status label
        self.status_label = tk.Label(
            root, textvariable=self.status_text,
            font=('Arial', status_size)
        )
        self.status_label.pack()

        # Counter label
        self.counter_label = tk.Label(
            root, textvariable=self.count_text,
            font=('Arial', count_size)
        )
        self.counter_label.pack(pady=(0,20))

        # Detect port
        self.PORT = detect_port()
        if not self.PORT:
            messagebox.showerror('Error', 'No ESP32 port found!')
            self.flash_button.config(state=tk.DISABLED)
            self.status_text.set('No ESP32 detected.')

    def load_count(self):
        try:
            with open(COUNT_FILE, 'r') as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def save_count(self):
        with open(COUNT_FILE, 'w') as f:
            f.write(str(self.flash_count))

    def play_sound(self, wav_path):
        self.root.bell()
        if os.path.exists(wav_path):
            subprocess.run(['aplay', wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_flash(self):
        self.flash_button.config(state=tk.DISABLED, bg='yellow')
        self.status_text.set('Flashing...')
        threading.Thread(target=self.flash_esp32, daemon=True).start()

    def flash_esp32(self):
        try:
            self.update_status('Erasing flash...')
            subprocess.run([
                'python3', '-m', 'esptool',
                '--chip', 'esp32',
                '--port', self.PORT,
                '--baud', BAUD,
                'erase_flash'
            ], check=True)

            self.update_status('Writing firmware...')
            subprocess.run([
                'python3', '-m', 'esptool',
                '--chip', 'esp32',
                '--port', self.PORT,
                '--baud', BAUD,
                'write_flash', '-z', '0x0', BIN
            ], check=True)

            self.update_status('Resetting ESP32...')
            subprocess.run([
                'python3', '-m', 'esptool',
                '--chip', 'esp32',
                '--port', self.PORT,
                '--baud', BAUD,
                'run'
            ], check=True)

            # Success
            self.flash_count += 1
            self.save_count()
            self.count_text.set(f'Flashes Completed: {self.flash_count}')
            self.update_status('✔ Flash complete.')
            self.flash_button.config(bg='green')
            self.play_sound(SUCCESS_WAV)

        except subprocess.CalledProcessError:
            self.update_status('❌ Flash failed.')
            self.flash_button.config(bg='red')
            self.play_sound(ERROR_WAV)
            messagebox.showerror('Error', 'Flash failed.')

        finally:
            self.flash_button.config(state=tk.NORMAL)

    def update_status(self, message):
        self.status_text.set(message)
        print(message)

if __name__ == '__main__':
    root = tk.Tk()
    app = FlashApp(root)
    root.mainloop()
