import asyncio
import websockets
import json
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from collections import deque
import numpy as np
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
from queue import Queue
import time

class OptimizedWaveDataPlotter:
    def __init__(self):
        # Data storage - increase for longer view
        self.max_points = 2000  # Keep last 2000 points for longer view
        self.timestamps = deque(maxlen=self.max_points)
        self.accel_x = deque(maxlen=self.max_points)
        self.accel_y = deque(maxlen=self.max_points)
        self.accel_z = deque(maxlen=self.max_points)
        self.force_z = deque(maxlen=self.max_points)
        
        # Settings
        self.mass = 1.0
        self.esp32_ip = "192.168.95.186"  # Updated default IP
        self.is_connected = False
        self.is_collecting = False
        self.websocket = None
        
        # Threading and data queue
        self.data_queue = Queue()
        self.websocket_thread = None
        
        # Performance optimization
        self.last_gui_update = 0
        self.gui_update_interval = 0.1  # Update GUI every 100ms instead of every data point
        self.last_plot_update = 0
        self.plot_update_interval = 0.05  # Update plots every 50ms
        
        # Setup integrated GUI
        self.setup_integrated_gui()
        
        # Start data processing
        self.process_data_queue()
        
    def setup_integrated_gui(self):
        # Main window
        self.root = tk.Tk()
        self.root.title("Wave Data Monitor - Integrated")
        self.root.geometry("1400x800")
        self.root.configure(bg='#f0f0f0')
        
        # Main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left panel for controls
        control_panel = ttk.LabelFrame(main_container, text="Controls", padding="10")
        control_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Connection settings
        conn_frame = ttk.LabelFrame(control_panel, text="Connection", padding="5")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(conn_frame, text="ESP32 IP:").pack(anchor=tk.W)
        self.ip_entry = ttk.Entry(conn_frame, width=20)
        self.ip_entry.insert(0, self.esp32_ip)
        self.ip_entry.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(conn_frame, text="Mass (kg):").pack(anchor=tk.W)
        self.mass_entry = ttk.Entry(conn_frame, width=20)
        self.mass_entry.insert(0, str(self.mass))
        self.mass_entry.pack(fill=tk.X, pady=(0, 5))
        
        # Status
        self.status_label = ttk.Label(conn_frame, text="Status: Disconnected", foreground="red")
        self.status_label.pack(pady=5)
        
        # Control buttons
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(btn_frame, text="Connect", command=self.connect_esp32)
        self.connect_btn.pack(fill=tk.X, pady=2)
        
        self.start_btn = ttk.Button(btn_frame, text="Start Collection", 
                                   command=self.start_data_collection, state=tk.DISABLED)
        self.start_btn.pack(fill=tk.X, pady=2)
        
        self.stop_btn = ttk.Button(btn_frame, text="Stop Collection", 
                                  command=self.stop_data_collection, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=2)
        
        self.clear_btn = ttk.Button(btn_frame, text="Clear Data", command=self.clear_data)
        self.clear_btn.pack(fill=tk.X, pady=2)
        
        # Data display
        data_frame = ttk.LabelFrame(control_panel, text="Current Values", padding="5")
        data_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.accel_label = ttk.Label(data_frame, text="Accel Z: -- m/s²")
        self.accel_label.pack(anchor=tk.W, pady=2)
        
        self.force_label = ttk.Label(data_frame, text="Force Z: -- N")
        self.force_label.pack(anchor=tk.W, pady=2)
        
        self.wave_height_label = ttk.Label(data_frame, text="Est. Wave Height: -- m")
        self.wave_height_label.pack(anchor=tk.W, pady=2)
        
        self.data_count_label = ttk.Label(data_frame, text="Data Points: 0")
        self.data_count_label.pack(anchor=tk.W, pady=2)
        
        # Right panel for plots
        plot_panel = ttk.Frame(main_container)
        plot_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Setup matplotlib in tkinter
        self.setup_embedded_plots(plot_panel)
        
    def setup_embedded_plots(self, parent):
        # Create matplotlib figure with better performance settings
        plt.style.use('default')  # Use default style for better performance
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(12, 8), 
                                                     facecolor='white')
        self.fig.suptitle('Real-time Wave Data from ESP32-C3 MPU6050', fontsize=14)
        
        # Acceleration plot
        self.ax1.set_title('Acceleration Z (Vertical Wave Motion)', fontsize=12)
        self.ax1.set_ylabel('Acceleration (m/s²)')
        self.ax1.grid(True, alpha=0.3)
        self.line1, = self.ax1.plot([], [], 'b-', linewidth=1.5, label='Accel Z')
        self.ax1.legend()
        self.ax1.set_xlim(0, 60)  # Show last 60 seconds
        
        # Force plot  
        self.ax2.set_title('Vertical Force (F = m × a_z)', fontsize=12)
        self.ax2.set_xlabel('Time (seconds)')
        self.ax2.set_ylabel('Force (N)')
        self.ax2.grid(True, alpha=0.3)
        self.line2, = self.ax2.plot([], [], 'r-', linewidth=1.5, label='Force Z')
        self.ax2.legend()
        self.ax2.set_xlim(0, 60)  # Show last 60 seconds
        
        plt.tight_layout()
        
        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Add navigation toolbar
        toolbar_frame = ttk.Frame(parent)
        toolbar_frame.pack(fill=tk.X)
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.update()
        
        # Start optimized animation with longer interval
        self.ani = animation.FuncAnimation(
            self.fig, self.update_plots, interval=100, blit=False, cache_frame_data=False
        )
        
    def connect_esp32(self):
        self.esp32_ip = self.ip_entry.get().strip()
        
        def test_connection():
            try:
                response = requests.get(f"http://{self.esp32_ip}/status", timeout=3)
                if response.status_code == 200:
                    self.root.after(0, self.connection_success)
                else:
                    self.root.after(0, lambda: self.connection_failed("ESP32 not responding"))
            except Exception as e:
                self.root.after(0, lambda: self.connection_failed(str(e)))
        
        # Test connection in background thread
        thread = threading.Thread(target=test_connection)
        thread.daemon = True
        thread.start()
        
        self.connect_btn.config(text="Connecting...", state=tk.DISABLED)
        
    def connection_success(self):
        self.is_connected = True
        self.status_label.config(text="Status: Connected", foreground="green")
        self.connect_btn.config(text="Connected", state=tk.DISABLED)
        self.start_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Success", "Connected to ESP32!")
        
    def connection_failed(self, error):
        self.connect_btn.config(text="Connect", state=tk.NORMAL)
        messagebox.showerror("Connection Error", f"Cannot connect to ESP32:\n{error}")
        
    def start_data_collection(self):
        try:
            self.mass = float(self.mass_entry.get())
            if self.mass <= 0:
                raise ValueError("Mass must be positive")
        except ValueError:
            messagebox.showerror("Input Error", "Please enter a valid positive mass")
            return
            
        self.is_collecting = True
        
        # Start WebSocket in background thread
        if self.websocket_thread is None or not self.websocket_thread.is_alive():
            self.websocket_thread = threading.Thread(target=self.start_websocket_client)
            self.websocket_thread.daemon = True
            self.websocket_thread.start()
        
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
    def stop_data_collection(self):
        self.is_collecting = False
        
        if self.websocket:
            try:
                # Send stop command
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self.websocket.send("stop"))
                loop.close()
            except:
                pass
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
    def clear_data(self):
        self.timestamps.clear()
        self.accel_x.clear()
        self.accel_y.clear()
        self.accel_z.clear()
        self.force_z.clear()
        
        # Update labels
        self.accel_label.config(text="Accel Z: -- m/s²")
        self.force_label.config(text="Force Z: -- N")
        self.wave_height_label.config(text="Est. Wave Height: -- m")
        self.data_count_label.config(text="Data Points: 0")
        
    def start_websocket_client(self):
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.websocket_client())
        except Exception as e:
            print(f"WebSocket thread error: {e}")
        finally:
            loop.close()
            
    async def websocket_client(self):
        uri = f"ws://{self.esp32_ip}/ws"
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                self.websocket = websocket
                print(f"Connected to {uri}")
                
                # Send start command
                await websocket.send("start")
                
                # Listen for data
                async for message in websocket:
                    if not self.is_collecting:
                        break
                        
                    try:
                        data = json.loads(message)
                        if 'accelX' in data:
                            # Put data in queue instead of direct processing
                            self.data_queue.put(data)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON: {message}")
                        
        except Exception as e:
            print(f"WebSocket error: {e}")
            if self.is_collecting:  # Only show error if we were actually collecting
                self.root.after(0, lambda: messagebox.showerror("WebSocket Error", str(e)))
        finally:
            self.websocket = None
            
    def process_data_queue(self):
        """Process data from queue - runs in main thread"""
        processed_count = 0
        max_process_per_cycle = 10  # Limit processing per cycle to prevent blocking
        
        while not self.data_queue.empty() and processed_count < max_process_per_cycle:
            try:
                data = self.data_queue.get_nowait()
                self.process_data_point(data)
                processed_count += 1
            except:
                break
                
        # Schedule next processing
        self.root.after(20, self.process_data_queue)  # Process every 20ms
        
    def process_data_point(self, data):
        # Add timestamp
        current_time = datetime.now()
        self.timestamps.append(current_time)
        
        # Store acceleration data
        accel_z_val = data.get('accelZ', 0)  # Use Z axis for vertical wave motion
        self.accel_x.append(data.get('accelX', 0))  # Still store X for reference
        self.accel_y.append(data.get('accelY', 0))
        self.accel_z.append(accel_z_val)
        
        # Calculate force F = m * a (using Z axis)
        force_z_val = self.mass * accel_z_val
        self.force_z.append(force_z_val)
        
        # Update GUI labels less frequently for better performance
        current_time_sec = time.time()
        if current_time_sec - self.last_gui_update > self.gui_update_interval:
            self.update_labels(accel_z_val, force_z_val)
            self.last_gui_update = current_time_sec
            
    def update_labels(self, accel_z, force_z):
        self.accel_label.config(text=f"Accel Z: {accel_z:.3f} m/s²")
        self.force_label.config(text=f"Force Z: {force_z:.3f} N")
        self.data_count_label.config(text=f"Data Points: {len(self.timestamps)}")
        
        # Estimate wave height from vertical acceleration
        if abs(accel_z) > 0.1:
            estimated_height = abs(accel_z) / (4 * np.pi**2) * 4
            self.wave_height_label.config(text=f"Est. Wave Height: {estimated_height:.3f} m")
        
    def update_plots(self, frame):
        """Optimized plot update function"""
        if len(self.timestamps) < 2:
            return []
            
        # Skip update if too soon (performance optimization)
        current_time = time.time()
        if current_time - self.last_plot_update < self.plot_update_interval:
            return []
        self.last_plot_update = current_time
        
        try:
            # Convert timestamps to seconds from start
            if len(self.timestamps) > 0:
                start_time = self.timestamps[0]
                time_seconds = [(t - start_time).total_seconds() for t in self.timestamps]
                
                # Update acceleration plot (Z axis)
                self.line1.set_data(time_seconds, list(self.accel_z))
                
                # Update force plot (Z axis)
                self.line2.set_data(time_seconds, list(self.force_z))
                
                # Auto-scale with buffer for better view
                if len(time_seconds) > 10:  # Only rescale if we have enough data
                    # Show longer time window for better overview
                    time_window = max(60, max(time_seconds))  # At least 60 seconds or current max
                    
                    self.ax1.set_xlim(max(0, max(time_seconds) - time_window), max(time_seconds) + 5)
                    self.ax2.set_xlim(max(0, max(time_seconds) - time_window), max(time_seconds) + 5)
                    
                    # Auto-scale Y with some padding
                    if self.accel_z:
                        accel_min, accel_max = min(self.accel_z), max(self.accel_z)
                        accel_range = accel_max - accel_min
                        if accel_range > 0:
                            padding = accel_range * 0.1
                            self.ax1.set_ylim(accel_min - padding, accel_max + padding)
                    
                    if self.force_z:
                        force_min, force_max = min(self.force_z), max(self.force_z)
                        force_range = force_max - force_min
                        if force_range > 0:
                            padding = force_range * 0.1
                            self.ax2.set_ylim(force_min - padding, force_max + padding)
                
        except Exception as e:
            print(f"Plot update error: {e}")
            
        return [self.line1, self.line2]
        
    def run(self):
        """Start the application"""
        def on_closing():
            self.is_collecting = False
            
            # Close WebSocket
            if self.websocket:
                try:
                    # Create new event loop to close websocket
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(self.websocket.close())
                    loop.close()
                except:
                    pass
            
            # Wait for thread to finish
            if self.websocket_thread and self.websocket_thread.is_alive():
                self.websocket_thread.join(timeout=1)
                
            self.root.destroy()
            
        self.root.protocol("WM_DELETE_WINDOW", on_closing)
        
        print("Starting Optimized Wave Data Plotter...")
        print(f"Default ESP32 IP: {self.esp32_ip}")
        print("Application ready!")
        
        # Start tkinter main loop
        self.root.mainloop()

if __name__ == "__main__":
    try:
        plotter = OptimizedWaveDataPlotter()
        plotter.run()
    except KeyboardInterrupt:
        print("\nApplication stopped by user")
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()