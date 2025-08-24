import serial, sys, time, psutil, os, bz2, gc, signal, threading, subprocess, struct, select, queue, termios, tty, contextlib

# Add OLED display support
try:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from oled_display import ImprovedOLEDDisplay
    OLED_AVAILABLE = True
except ImportError:
    OLED_AVAILABLE = False
    print("OLED display not available - continuing with console only")

# Global flag for shutdown
shutdown_requested = False
STOP_FILE = "/tmp/taskun_stop"

# Global OLED display instance
oled_display = None

def signal_handler(signum, frame):
    """Handle interrupt signals for graceful shutdown"""
    global shutdown_requested
    print("\n--- Shutdown signal received, stopping playback...")
    shutdown_requested = True
    _cleanup_oled_display()

def check_stop_file():
    """Check if stop file exists"""
    global shutdown_requested
    if os.path.exists(STOP_FILE):
        shutdown_requested = True
        print("\n--- Stop file detected, stopping playback...")
        try:
            os.remove(STOP_FILE)
        except:
            pass

# ---------------------------
# Interactive menu utilities
# ---------------------------

def _list_r08_files():
    """Return sorted list of .r08 files in the tasmovies directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tasmovies_dir = os.path.join(script_dir, "tasmovies")
    try:
        files = [os.path.join(tasmovies_dir, f) for f in os.listdir(tasmovies_dir) if f.lower().endswith('.r08')]
    except Exception:
        files = []
    files.sort(key=lambda p: os.path.basename(p).lower())
    return files

def _list_replay_files():
    """Return sorted list of supported replay files (.r08) in tasmovies dir."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tasmovies_dir = os.path.join(script_dir, "tasmovies")
    try:
        files = [os.path.join(tasmovies_dir, f) for f in os.listdir(tasmovies_dir) if f.lower().endswith('.r08')]
    except Exception:
        files = []
    files.sort(key=lambda p: os.path.basename(p).lower())
    return files


class _JoystickReader(threading.Thread):
    """Minimal joystick reader using /dev/input/js0 for navigation and stop.

    - Axis 1 or 7 (vertical): up/down navigation when past threshold
    - Button 0 (A): select
    - Button 1 (B): stop/back
    """

    JS_EVENT_BUTTON = 0x01
    JS_EVENT_AXIS = 0x02
    JS_EVENT_INIT = 0x80

    def __init__(self, device_path='/dev/input/js0'):
        super().__init__(daemon=True)
        self.device_path = device_path
        self.fd = None
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self._last_nav_time = 0.0
        self._nav_cooldown_s = 0.18

    def run(self):
        try:
            self.fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
        except Exception:
            self.fd = None
        if self.fd is None:
            return
        buf = b''
        while not self.stop_event.is_set():
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if not r:
                continue
            try:
                chunk = os.read(self.fd, 8 * 16)
            except Exception:
                break
            if not chunk:
                continue
            buf += chunk
            while len(buf) >= 8:
                ev = buf[:8]
                buf = buf[8:]
                try:
                    time_ms, value, etype, number = struct.unpack('<IhBB', ev)
                except Exception:
                    continue
                if etype & self.JS_EVENT_INIT:
                    etype = etype & ~self.JS_EVENT_INIT
                now = time.time()
                if etype == self.JS_EVENT_AXIS:
                    if number in (1, 7):  # vertical axis
                        if value < -15000 and (now - self._last_nav_time) > self._nav_cooldown_s:
                            self._put('up')
                            self._last_nav_time = now
                        elif value > 15000 and (now - self._last_nav_time) > self._nav_cooldown_s:
                            self._put('down')
                            self._last_nav_time = now
                elif etype == self.JS_EVENT_BUTTON:
                    if number == 1 and value == 1:  # A button (mapped to select)
                        self._put('select')
                    elif number == 0 and value == 1:  # B button (mapped to stop/back)
                        self._put('stop')

        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass

    def _put(self, event_name):
        try:
            if self.events.qsize() < 32:
                self.events.put_nowait(event_name)
        except Exception:
            pass

    def get_event(self):
        try:
            return self.events.get_nowait()
        except Exception:
            return None


def _touch_stop_file():
    try:
        with open(STOP_FILE, 'a'):
            os.utime(STOP_FILE, None)
    except Exception:
        pass


def _launch_playback(selected_path, port=None):
    """Spawn this script as a child to run the selected replay.

    Child prints are suppressed to keep curses UI intact.
    """
    if port is None:
        port = ('COM3' if os.name == 'nt' else '/dev/ttyACM0')
    # Ensure no stale stop file
    try:
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)
    except Exception:
        pass
    args = [sys.executable, os.path.abspath(__file__), port, selected_path]
    try:
        # Allow stdout/stderr to pass through for debugging
        proc = subprocess.Popen(args)
    except Exception as e:
        return None, str(e)
    return proc, None


@contextlib.contextmanager
def _raw_stdin_if_tty():
    """Put stdin in cbreak mode if it's a TTY, restore on exit."""
    if not sys.stdin.isatty():
        # Non-interactive stdin (e.g., service). No key input available.
        yield False
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield True
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass


def _clear_and_print_lines(line1, line2):
    # Print two lines for console only (avoid touching OLED here)
    # No longer clearing screen to keep previous output visible
    print(line1)
    print(line2)
    sys.stdout.flush()

def _init_oled_display():
    """Initialize OLED display if available"""
    global oled_display
    if OLED_AVAILABLE:
        try:
            oled_display = ImprovedOLEDDisplay()
            oled_display.clear()
            oled_display.write_text("TASKUN V1", 1, 10)
            oled_display.write_text("LOADING...", 2, 10)
            return True
        except Exception as e:
            print(f"Failed to initialize OLED display: {e}")
            oled_display = None
    return False

def _cleanup_oled_display():
    """Clean up OLED display"""
    global oled_display
    if oled_display:
        try:
            oled_display.clear()
            oled_display.close()
        except Exception:
            pass
        oled_display = None

def _reset_cy8ckit_device(port):
    """Reset the CY8CKIT-059 device to stop any ongoing operations"""
    try:
        # Try to connect and send reset command
        ser = serial.Serial(port, 2000000, timeout=0.1)
        ser.write(b'\x00')  # Reset command
        time.sleep(0.1)
        ser.close()
        print("--- CY8CKIT-059 device reset")
        return True
    except Exception as e:
        print(f"--- Warning: Could not reset CY8CKIT-059 device: {e}")
        return False

def _show_oled_menu(files, idx, header=None, old_idx=None):
    """Show menu on OLED display with efficient selection updates"""
    global oled_display
    if oled_display and OLED_AVAILABLE:
        try:
            if not files:
                oled_display.show_status("TASKUN V1", "No .r08 files", "found in tasmovies", "")
                return
            
            # Create list of filenames for OLED display
            filenames = [os.path.basename(f) for f in files]
            window_size = 8
            
            # Initialize state if needed
            if not hasattr(_show_oled_menu, 'current_start_idx'):
                _show_oled_menu.current_start_idx = 0
                _show_oled_menu.last_displayed_items = []
            
            current_start = _show_oled_menu.current_start_idx
            current_end = current_start + window_size
            
            # Check if we need to page to a new screen
            need_full_redraw = False
            
            if old_idx is None:
                # Initial draw
                need_full_redraw = True
            elif idx < current_start:
                # Selection moved above current window - page up 
                # Put selection near bottom of new page for clean paging
                if idx < window_size:
                    # First page
                    _show_oled_menu.current_start_idx = 0
                else:
                    # Try to put selection on line 7 of new page
                    _show_oled_menu.current_start_idx = max(0, idx - (window_size - 2))
                need_full_redraw = True
            elif idx >= current_end:
                # Selection moved below current window - page down
                # Put selection near top of new page for clean paging  
                if idx >= len(filenames) - window_size:
                    # Last page - show as many items as possible
                    _show_oled_menu.current_start_idx = max(0, len(filenames) - window_size)
                else:
                    # Try to put selection on line 2 of new page
                    _show_oled_menu.current_start_idx = max(0, idx - 1)
                need_full_redraw = True
            
            start_idx = _show_oled_menu.current_start_idx
            
            if need_full_redraw:
                # Full redraw when paging or initial display
                oled_display.show_menu_window("TASKUN V1", filenames, idx, start_idx)
                _show_oled_menu.last_displayed_items = filenames[start_idx:start_idx + window_size]
            else:
                # Efficient update: just move the selection marker and update counter
                old_line = (old_idx - start_idx + 1) if old_idx is not None else 0
                new_line = idx - start_idx + 1
                
                # Update counter
                oled_display.update_counter_only(idx, len(filenames))
                
                # Move selection marker efficiently
                if 1 <= old_line <= 8 and 1 <= new_line <= 8:
                    oled_display.move_selection_marker(filenames, old_line, new_line, start_idx)
                else:
                    # Fallback to line-by-line update if marker movement fails
                    oled_display.update_menu_selection_window(filenames, old_idx, idx, start_idx)
                    
        except Exception as e:
            print(f"OLED menu error: {e}")

def _show_famicom_instructions():
    """Show Famicom setup instructions"""
    global oled_display
    if oled_display and OLED_AVAILABLE:
        try:
            oled_display.show_status(
                "SETUP FAMICOM:",
                "Turn OFF Famicom",
                "Push A to continue",
                "(B to go back)",
            )
        except Exception as e:
            print(f"OLED instruction error: {e}")
    
    print("\n" + "="*50)
    print("FAMICOM SETUP INSTRUCTIONS:")
    print("- Turn OFF the Famicom")
    print("- Push A to start replay (B to go back)")
    print("- After it starts: Turn ON the Famicom, then press RESET")
    print("="*50)


def _minimal_menu():
    files = _list_replay_files()
    # Manual control disabled - PSoC firmware not suitable for real-time input
    # menu_items = ["Manual control"] + files
    menu_items = files
    idx = 0
    
    # Initialize OLED display
    oled_initialized = _init_oled_display()
    if oled_initialized:
        print("OLED display initialized")
    else:
        print("OLED display not available - using console only")
    
    joy = _JoystickReader('/dev/input/js0')
    try:
        joy.start()
    except Exception:
        pass

    # Paging state for OLED menu
    current_page_start = 0  # index of first item in current window

    def draw(header, old_idx=None):
        if not menu_items:
            _clear_and_print_lines('Taskun: 0 items (q=quit)', 'No .r08 files found')
            _show_oled_menu([], idx, header, old_idx)
            return
        total = len(menu_items)
        # Manual control removed - just show file names
        name = os.path.basename(menu_items[idx])
        line1 = f'Taskun: {total} files (q=quit)'
        line2 = f'> {name}'
        if header:
            line1 = header[:32]
        _clear_and_print_lines(line1, line2[:80])
        # Pass the display names for OLED, not full paths
        # display_names = ["Manual control"] + [os.path.basename(f) for f in files]
        display_names = [os.path.basename(f) for f in files]
        _show_oled_menu(display_names, idx, header, old_idx)

    draw('Select option (w/s + Enter)')
    with _raw_stdin_if_tty() as has_tty:
        while True:
            # Keyboard
            ch = None
            if has_tty:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    try:
                        ch = sys.stdin.read(1)
                    except Exception:
                        ch = None
            # Joystick
            evt = joy.get_event() if joy else None

            if shutdown_requested:
                return
            if ch in ('w', 'k') or evt == 'up':
                if menu_items:
                    old_idx = idx
                    idx = (idx - 1) % len(menu_items)
                    draw(None, old_idx)
            elif ch in ('s', 'j') or evt == 'down':
                if menu_items:
                    old_idx = idx
                    idx = (idx + 1) % len(menu_items)
                    draw(None, old_idx)
            elif ch in ('\n', '\r') or evt == 'select':
                if shutdown_requested:
                    return
                if not menu_items:
                    continue
                
                # Manual control removed - all items are now TAS replay files
                # TAS replay mode
                selected = menu_items[idx]
                filename = os.path.basename(selected)
                
                # Show Famicom setup instructions
                _show_famicom_instructions()
                
                # Wait for user to complete setup (A to start, B to back)
                print("\nPress A to start replay, or B to go back...")
                with _raw_stdin_if_tty() as has_tty_setup:
                    while True:
                        ch_setup = None
                        if has_tty_setup:
                            r_setup, _, _ = select.select([sys.stdin], [], [], 0.05)
                            if r_setup:
                                try:
                                    ch_setup = sys.stdin.read(1)
                                except Exception:
                                    ch_setup = None
                        evt_setup = joy.get_event() if joy else None
                        
                        if shutdown_requested:
                            return
                        # Keyboard: Enter starts, q cancels. Joystick: A starts (select), B cancels (stop)
                        if evt_setup == 'stop' or ch_setup in ('q', 'Q'):
                            draw('Select option (w/s + Enter)')
                            break
                        if ch_setup in ('\n', '\r') or evt_setup == 'select':
                            break
                        time.sleep(0.02)
                    
                    _clear_and_print_lines('Launching...', filename)
                    proc, err = _launch_playback(selected)
                    if err:
                        draw(f'Error: {err}')
                        # Reset the CY8CKIT-059 device on error
                        port = ('COM3' if os.name == 'nt' else '/dev/ttyACM0')
                        _reset_cy8ckit_device(port)
                        time.sleep(1.0)
                        draw('Select option (w/s + Enter)')
                        continue
                    _clear_and_print_lines('Playing (press key/B to stop)', filename)
                    # Safe to update OLED from parent (avoid child timing impact)
                    if oled_display and OLED_AVAILABLE:
                        try:
                            oled_display.show_status(
                                "REPLAY STARTED:",
                                "Turn ON Famicom",
                                "Then press RESET",
                                "B to stop replay",
                            )
                        except Exception:
                            pass
                    # During playback, any key or joystick B will stop
                    with _raw_stdin_if_tty() as has_tty2:
                        while proc.poll() is None:
                            ch2 = None
                            if has_tty2:
                                rr, _, _ = select.select([sys.stdin], [], [], 0.05)
                                if rr:
                                    try:
                                        ch2 = sys.stdin.read(1)
                                    except Exception:
                                        ch2 = None
                            evt2 = joy.get_event() if joy else None
                            if shutdown_requested:
                                _touch_stop_file()
                                break
                            if ch2 is not None or evt2 == 'stop':
                                _touch_stop_file()
                                # Send stop signal immediately
                                try:
                                    proc.send_signal(signal.SIGINT)
                                except Exception:
                                    pass
                                # Force stop if needed
                                try:
                                    proc.terminate()
                                except Exception:
                                    pass
                                # Wait briefly for exit
                                for _ in range(50):
                                    if proc.poll() is not None:
                                        break
                                    time.sleep(0.02)
                                if proc.poll() is None:
                                    try:
                                        proc.kill()
                                    except Exception:
                                        pass
                                
                                # Don't reset immediately - let the child process handle the wait
                                break
                            # Also check stop file externally
                            time.sleep(0.02)
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                
                # Don't reset here - the child process will handle the reset after button press
                try:
                    if os.path.exists(STOP_FILE):
                        os.remove(STOP_FILE)
                except Exception:
                    pass
                # Single redraw back to menu
                draw('Select option (w/s + Enter)')
            elif ch in ('q', 'Q'):
                if joy:
                    joy.stop_event.set()
                _clear_and_print_lines('Bye', '')
                _cleanup_oled_display()
                return
            else:
                time.sleep(0.02)

# disable gc
gc.disable()
	
# give us high priority
p = psutil.Process(os.getpid())

#p.nice(psutil.REALTIME_PRIORITY_CLASS)

try:
    p.nice(-20)   # highest priority allowed for normal user (may need sudo)
except Exception as e:
    print("Could not set realtime priority:", e)

# Set up signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Remove any existing stop file
try:
    os.remove(STOP_FILE)
except:
    pass

def run_playback(port, movie_path):
    # args:  python3 taskun_r08.py <serialDevice> <movie.r08>
    print(f"\n+++ Starting playback of {movie_path}")
    if movie_path is None:
        print("Usage: taskun_r08.py <serialDevice> <movie.r08>")
        return 1

    # 2,000,000 baud is what the repo uses; keep it unless you have trouble
    print(f"+++ Opening serial port {port} at 2000000 baud")
    try:
        ser = serial.Serial(port, 2000000, timeout=0.5)
    except Exception as e:
        print(f"!!! Failed to open serial port: {e}")
        return 2

    # send "ping" command to make sure device is there
    print("+++ Sending ping command (0xFF)")
    ser.write(b'\xFF')
    data = ser.read()
    if data == b'\xFF':
        print("+++ Connected to device, device is ready to receive commands...")
    else:
        print(f"!!! Device is not ready, got response: {data.hex() if data else 'None'}")
        return 2

    f = None
    filename = movie_path
    print(f"+++ Opening file: {filename}")
    try:
        if filename[-3:].lower() == "bz2":
            f = bz2.BZ2File(filename, "r")
        else:    
            f = open(filename, "rb")
        # Get file size
        file_size = f.seek(0, 2)
        f.seek(0)
        print(f"+++ File opened successfully, size: {file_size} bytes ({file_size//2} frames)")
    except Exception as e:
        print(f"!!! Failed to open file: {e}")
        return 3

    # reset device
    print("--- Sending reset command to device")
    ser.write(b'\x00')
    time.sleep(0.1)

    # start run
    print("--- Sending start command to device")
    ser.write(b'\x01\x01\x02\x01\x00\x01\x00') # command 1 (play), 8-bits, 2 ports, 1 dataline, sync, use window on port 1, unused in sync mode

    latches = 0
    skip = 0
    extra = 0

    for n in range(0, skip):
        f.read(2)

    cmd = None
    data = None
    inputs = None
    tmp = None
	
    print("--- Starting read loop (Press Ctrl+C to stop, or run 'touch /tmp/taskun_stop' in another terminal)")
    
    # Note: Avoid OLED writes in child during timing-critical start
    
    while not shutdown_requested:
        cmd = ser.read()
        if not cmd:  # Timeout occurred
            # Debug: count consecutive timeouts
            if not hasattr(run_playback, 'timeout_count'):
                run_playback.timeout_count = 0
            run_playback.timeout_count += 1
            if run_playback.timeout_count > 10:  # More than 5 seconds of no response
                print(f"\n=== PLAYBACK STOPPED: Device timeout ===")
                print(f"No response from device for {run_playback.timeout_count * 0.5:.1f} seconds")
                print(f"Last frame played: {latches}")
                print(f"File position: {f.tell()} bytes")
                print(f"File size: {f.seek(0, 2)} bytes")
                f.seek(f.tell())  # Reset position
                print(f"Bytes remaining: {f.seek(0, 2) - f.tell()}")
                break
            continue
        else:
            run_playback.timeout_count = 0  # Reset timeout counter on successful read
        if cmd == b'\x0F':
            # device wants input
            if extra > 0:
                inputs = f.read(60 - (extra*2))
                tmp = ([0]*(extra*2)) + [x for x in inputs]
                # Send response with 0x0F prefix
                response_data = bytes([0x0F] + tmp)
                # Removed 0x00 warnings as they were not useful
                ser.write(response_data)
                extra = 0
            else:
                inputs = f.read(60)
                if not inputs:  # End of file reached
                    print("\n=== PLAYBACK STOPPED: End of file reached ===")
                    print(f"Last frame played: {latches}")
                    print(f"File position: {f.tell()} bytes")
                    print(f"Total time: {latches/60:.1f} seconds")
                    break
                # Removed verbose frame logging
                # Pad with zeros if we got less than 60 bytes
                if len(inputs) < 60:
                    # This is normal at end of file, no need for a warning
                    inputs = inputs + bytes(60 - len(inputs))
                # Send response with 0x0F prefix
                response_data = bytes([0x0F] + [x for x in inputs])
                # Removed 0x00 warnings as they were not useful
                ser.write(response_data)
                
            latches = latches + 30
            # Debug output every ~10 seconds
            if latches % 600 == 0:
                print(f'*** Progress: {latches} latches ({latches/60:.1f} seconds), file position: {f.tell()} bytes')
            
            # Debug logging removed
        
        # Check for stop file every 100 latches (about every 3 seconds)
        if latches % 100 == 0:
            check_stop_file()
        if shutdown_requested:
            print(f"\n=== PLAYBACK STOPPED: User interrupt ===")
            print(f"Last frame played: {latches}")
            print(f"File position: {f.tell()} bytes")
            print(f"Total time: {latches/60:.1f} seconds")
            break
        
        # Check for unexpected responses from device
        elif cmd and cmd != b'\x0F':
            print(f"\n--- WARNING: Unexpected response from device: {cmd.hex()}")
            print(f"--- At frame {latches}, file position {f.tell()}")
            # Log the last data we sent
            if inputs:
                print(f"--- Last data sent: {' '.join(f'{b:02X}' for b in inputs[:10])}...")
            # Don't break, just log it
            continue

    # Check if we exited without explicit break (device stopped requesting)
    if not shutdown_requested and f and f.tell() < f.seek(0, 2):
        print(f"\n=== PLAYBACK STOPPED: Device stopped requesting data ===")
        print(f"Last frame played: {latches}")
        print(f"File position: {f.tell()} bytes")
        print(f"File size: {f.seek(0, 2)} bytes")
        print(f"Frames remaining in file: {(f.seek(0, 2) - f.tell())//2}")
        print(f"Last command from device: {cmd.hex() if cmd else 'None'}")
    
    # Final summary
    print(f"\n=== PLAYBACK SUMMARY ===")
    print(f"Total frames processed: {latches}")
    print(f"Total time: {latches/60:.1f} seconds ({latches/60/60:.2f} minutes)")
    if f:
        print(f"Expected frames in file: {f.seek(0, 2)//2}")
        print(f"Frames remaining: {(f.seek(0, 2) - f.tell())//2}")
    
    # Cleanup - close file but keep device running
    print("\n--- Cleaning up...")
    if f:
        f.close()
    
    # Only show wait message if playback ended naturally (not user-interrupted)
    if not shutdown_requested:
        # Show message on OLED and wait for button B
        print("\n--- TAS data transmission complete")
        print("--- Press B button to return to main menu")
        
        global oled_display
        if oled_display and OLED_AVAILABLE:
            try:
                oled_display.show_status(
                    "DONE SENDING DATA",
                    "TAS complete",
                    "Press B for",
                    "main menu"
                )
            except Exception as e:
                print(f"Failed to update OLED: {e}")
        
        # Initialize joystick reader for button detection
        joy = _JoystickReader('/dev/input/js0')
        try:
            joy.start()
        except Exception:
            pass
        
        # Wait for button B press (or keyboard 'q' as fallback)
        print("--- Waiting for button press...")
        with _raw_stdin_if_tty() as has_tty:
            while True:
                # Check keyboard
                ch = None
                if has_tty:
                    r, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r:
                        try:
                            ch = sys.stdin.read(1)
                        except Exception:
                            ch = None
                
                # Check joystick
                evt = joy.get_event() if joy else None
                
                # Exit on B button or 'q' key
                if evt == 'stop' or ch in ('q', 'Q', 'b', 'B'):
                    break
                    
                # Also check for shutdown signal
                if shutdown_requested:
                    break
                    
                time.sleep(0.02)
        
        # Stop joystick reader
        if joy:
            joy.stop_event.set()
    else:
        print("\n--- Playback interrupted by user")
    
    # Now reset the device
    print("\n--- Resetting device...")
    if ser:
        # Send reset command to stop the device
        ser.write(b'\x00')
        time.sleep(0.1)
        ser.close()
    
    # Additional reset to ensure device is stopped
    _reset_cy8ckit_device(port)
    
    print("--- Shutdown complete")
    return 0


if __name__ == "__main__":
    # If no args, show minimal menu; else, run playback directly
    if len(sys.argv) < 3:
        _minimal_menu()
    else:
        port = sys.argv[1]
        movie_path = sys.argv[2]
        exit_code = run_playback(port, movie_path)
        try:
            sys.exit(exit_code)
        except SystemExit:
            pass
