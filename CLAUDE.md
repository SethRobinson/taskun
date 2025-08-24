# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TASkun is a Raspberry Pi-based menu system for the TASBot replay device, enabling playback of tool-assisted speedruns on real NES/Famicom hardware. The system features an OLED display interface, USB gamepad support, and automatic service management.

## Key Commands

### Running the Replay System
```bash
# Install dependencies
pip3 install -r requirements.txt
# Or manually: pip3 install luma.oled luma.core Pillow smbus2

# Run the interactive menu (default mode)
python3 taskun_r08.py

# Run with specific serial port and movie file
python3 taskun_r08.py <serialDevice> <movie.r08>
```

Serial device examples: `/dev/ttyACM0` (Linux), `COM3` (Windows), `/dev/tty.usbmodem1411` (macOS)

### Service Management
```bash
# Set up automatic startup on boot
./setup_autostart.sh

# Start the service manually
./start_taskun_manually.sh

# Stop the service
./stop_taskun_service.sh

# Check service status
sudo systemctl status taskun.service

# View logs
sudo journalctl -u taskun.service -f
```

## Architecture

### Core Components
- **taskun_r08.py**: Main application handling menu navigation, serial communication with TASBot hardware, and playback control
  - Interactive menu system with keyboard/gamepad input
  - High-priority process scheduling for timing accuracy
  - Garbage collection disabled during playback
  - Serial communication at 2,000,000 baud rate
  
- **oled_display.py**: OLED display driver providing visual feedback
  - I2C communication with SSD1306 display
  - Menu rendering and status updates
  
- **tasmovies/**: Directory containing .r08 replay files
  - Files are automatically discovered and displayed in the menu
  - Sorted alphabetically for navigation

### Communication Protocol
The system communicates with the CY8CKIT-059 (PSoC 5LP) hardware via serial:
- `0xFF`: Ping/connection test
- `0x00`: Reset device
- `0x01`: Start playback with configuration bytes
- `0x0F`: Device requests input data (30 frames at a time)
- Device operates in synchronous mode, requesting data as needed

### Hardware Requirements
- Raspberry Pi with I2C enabled
- 1.3" I2C OLED display (SSD1306) at address 0x3c
- CY8CKIT-059 (PSoC 5LP) with TASBot firmware
- USB gamepad for navigation (optional)
- NES/Famicom console with controller port adapter