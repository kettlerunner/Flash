#!/usr/bin/env python3
import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import glob
import os

# Firmware and settings
BIN = '/home/pi/FR1_FACTORY.bin'
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
        # Borderless fullscreen and hide cursor
        root.withdraw()
        root.overrideredirect(True)
        root.attributes('-fullscreen', True, '-topmost', True)
        root.config(cursor='none')
        root.update_idletasks()
        # Geometry ensures full coverage
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.geometry(f"{width}x{height}+0+0")
        root.deiconify()

        # UI frames
        btn_frame = tk.Frame(root, bg='#333')
        btn_frame.pack(fill='x', pady=5)

        # Buttons
        self.flash_button = tk.Button(
            btn_frame, text='Flash', font=('Arial', 20), bg='green', fg='white',
            width=10, command=self.start_flash
        )
        self.flash_button.pack(side='left', padx=10)

        self.reset_button = tk.Button(
            btn_frame, text='Reset', font=('Arial', 20), bg='orange', fg='white',
            width=10, command=self.reset_ui
        )
        self.reset_button.pack(side='left', padx=10)

        self.close_button = tk.Button(
            btn_frame, text='Close', font=('Arial', 20), bg='red', fg='white',
            width=10, command=root.quit
        )
        self.close_button.pack(side='right', padx=10)

        # Status log area
        self.log_area = scrolledtext.ScrolledText(
            root, state='disabled', font=('Courier', 14), bg='#111', fg='#0f0', wrap='word'
        )
        self.log_area.pack(expand=True, fill='both', padx=10, pady=(0,10))

        # Initialize
        self.flash_count = self.load_count()
        self.PORT = detect_port()
        if not self.PORT:
            self.log('Error: No ESP32 port found!')
            self.flash_button.config(state='disabled', bg='grey')

    def load_count(self):
        try:
            with open(COUNT_FILE, 'r') as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def save_count(self):
        with open(COUNT_FILE, 'w') as f:
            f.write(str(self.flash_count))

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert('end', message + '\n')
        self.log_area.yview('end')
        self.log_area.config(state='disabled')
        print(message)

    def play_sound(self, wav_path):
        self.root.bell()
        if os.path.exists(wav_path):
            subprocess.run(['aplay', wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

            self.log('Writing firmware...')
            subprocess.run([
                'python3', '-m', 'esptool', '--chip', 'esp32',
                '--port', self.PORT, '--baud', BAUD,
                'write_flash', '-z', '0x0', BIN
            ], check=True)

            self.log('Resetting ESP32...')
            subprocess.run([
                'python3', '-m', 'esptool', '--chip', 'esp32',
                '--port', self.PORT, '--baud', BAUD, 'run'
            ], check=True)

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
        # Clear logs and reset button states
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', 'end')
        self.log_area.config(state='disabled')
        self.flash_button.config(state='normal', bg='green')
        self.log('UI reset. Ready.')

if __name__ == '__main__':
    root = tk.Tk()
    app = FlashApp(root)
    root.mainloop()
