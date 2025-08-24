#!/usr/bin/env python3
"""
Improved OLED Display Class
Optimized for better performance and more text lines
"""

import time
import smbus2

class ImprovedOLEDDisplay:
    def __init__(self, bus=1, address=0x3c):
        """Initialize OLED display"""
        self.bus = smbus2.SMBus(bus)
        self.address = address
        self.width = 128
        self.height = 64
        self.current_buffer = [[0] * 128 for _ in range(8)]  # 8 pages x 128 columns
        self.init_display()
        
    def write_cmd(self, cmd):
        """Write a command to the display"""
        self.bus.write_byte_data(self.address, 0x00, cmd)
            
    def write_data(self, data):
        """Write data to the display"""
        self.bus.write_byte_data(self.address, 0x40, data)
    
    def write_data_bulk(self, data_list):
        """Write multiple data bytes at once for better performance"""
        for data in data_list:
            self.write_data(data)
    
    def clear_line(self, page):
        """Clear a single text line (page) efficiently"""
        if page < 0 or page > 7:
            return
        self.set_position(page, 0)
        self.write_data_bulk([0x00] * 128)
    
    def init_display(self):
        """Initialize the display"""
        # Basic initialization sequence for SSD1306
        init_commands = [
            0xAE,  # Display off
            0xD5,  # Set display clock
            0x80,  # Clock div
            0xA8,  # Set multiplex ratio
            0x3F,  # 64 rows
            0xD3,  # Set display offset
            0x00,  # No offset
            0x40,  # Set start line
            0x8D,  # Charge pump
            0x14,  # Enable charge pump
            0x20,  # Memory mode
            0x00,  # Horizontal addressing
            0xA1,  # Segment remap
            0xC8,  # COM scan direction
            0xDA,  # COM pins
            0x12,  # COM pins config
            0x81,  # Contrast
            0xCF,  # Contrast value
            0xD9,  # Pre-charge
            0xF1,  # Pre-charge timing
            0xDB,  # VCOM detect
            0x40,  # VCOM detect level
            0xA4,  # Display all on resume
            0xA6,  # Normal display
            0xAF,  # Display on
        ]
        
        for cmd in init_commands:
            self.write_cmd(cmd)
            time.sleep(0.0005)  # Reduced delay for faster initialization
    
    def clear(self):
        """Clear the display buffer and screen"""
        # Clear buffer
        self.current_buffer = [[0] * 128 for _ in range(8)]
        
        # Clear screen efficiently
        for page in range(8):
            self.write_cmd(0xB0 + page)  # Set page
            self.write_cmd(0x02)         # Set lower column
            self.write_cmd(0x10)         # Set higher column
            self.write_data_bulk([0x00] * 128)  # Bulk write zeros
    
    def set_position(self, page, col):
        """Set cursor position"""
        self.write_cmd(0xB0 + page)  # Set page
        self.write_cmd(0x02 + (col & 0x0F))  # Set lower column
        self.write_cmd(0x10 + (col >> 4))    # Set higher column
    
    def write_text(self, text, page, col=0):
        """Write text at specified position"""
        # Simple 8x8 font pattern (optimized for 8x6 characters)
        font_8x6 = {
            'A': [0x7E, 0x11, 0x11, 0x7E],
            'B': [0x7F, 0x49, 0x49, 0x36],
            'C': [0x3E, 0x41, 0x41, 0x22],
            'D': [0x7F, 0x41, 0x22, 0x1C],
            'E': [0x7F, 0x49, 0x49, 0x41],
            'F': [0x7F, 0x09, 0x09, 0x01],
            'G': [0x3E, 0x41, 0x49, 0x7A],
            'H': [0x7F, 0x08, 0x08, 0x7F],
            'I': [0x41, 0x7F, 0x41],
            'J': [0x20, 0x40, 0x3F, 0x01],
            'K': [0x7F, 0x08, 0x14, 0x63],
            'L': [0x7F, 0x40, 0x40, 0x40],
            'M': [0x7F, 0x02, 0x0C, 0x02, 0x7F],
            'N': [0x7F, 0x04, 0x08, 0x7F],
            'O': [0x3E, 0x41, 0x41, 0x3E],
            'P': [0x7F, 0x09, 0x09, 0x06],
            'Q': [0x3E, 0x41, 0x51, 0x5E],
            'R': [0x7F, 0x09, 0x19, 0x66],
            'S': [0x46, 0x49, 0x49, 0x31],
            'T': [0x01, 0x7F, 0x01],
            'U': [0x3F, 0x40, 0x40, 0x3F],
            'V': [0x1F, 0x20, 0x40, 0x20, 0x1F],
            'W': [0x3F, 0x40, 0x38, 0x40, 0x3F],
            'X': [0x63, 0x14, 0x08, 0x14, 0x63],
            'Y': [0x07, 0x08, 0x70, 0x08, 0x07],
            'Z': [0x61, 0x51, 0x49, 0x45, 0x43],
            ' ': [0x00, 0x00, 0x00],
            '!': [0x5F],
            '0': [0x3E, 0x51, 0x49, 0x3E],
            '1': [0x42, 0x7F, 0x40],
            '2': [0x42, 0x61, 0x51, 0x46],
            '3': [0x21, 0x45, 0x4B, 0x31],
            '4': [0x18, 0x14, 0x12, 0x7F],
            '5': [0x27, 0x45, 0x45, 0x39],
            '6': [0x3C, 0x4A, 0x49, 0x30],
            '7': [0x01, 0x71, 0x09, 0x03],
            '8': [0x36, 0x49, 0x49, 0x36],
            '9': [0x06, 0x49, 0x29, 0x1E],
            '.': [0x00],
            ':': [0x36],
            '-': [0x08, 0x08, 0x08],
            '_': [0x40, 0x40, 0x40],
            '>': [0x41, 0x22, 0x14, 0x08],
            '<': [0x08, 0x14, 0x22, 0x41],
            '=': [0x14, 0x14, 0x14],
            '+': [0x08, 0x08, 0x3E, 0x08, 0x08],
            '/': [0x60, 0x18, 0x06, 0x01],
            '*': [0x14, 0x08, 0x3E, 0x08, 0x14],
        }
        
        self.set_position(page, col)
        
        for char in text.upper():
            if char in font_8x6:
                pattern = font_8x6[char]
                for byte in pattern:
                    self.write_data(byte)
                # Add minimal space between characters
                self.write_data(0x00)
    
    def write_multiline(self, lines, start_page=0):
        """Write multiple lines of text efficiently"""
        for i, line in enumerate(lines):
            if start_page + i < 8:  # Ensure we don't exceed display height
                self.write_text(line, start_page + i, 0)
    
    def draw_border(self):
        """Draw a border around the display"""
        # Top and bottom borders
        for page in [0, 7]:
            self.set_position(page, 0)
            self.write_data_bulk([0xFF] * 128)
        
        # Left and right borders
        for page in range(8):
            self.set_position(page, 0)
            self.write_data(0xFF)
            self.set_position(page, 127)
            self.write_data(0xFF)
    
    def show_menu(self, title, items, selected_idx, total_items):
        """Display a menu with title and file list"""
        self.clear()
        
        # Show title
        self.write_text(title, 0, 0)
        
        # Show file count
        count_text = f"{selected_idx + 1}/{total_items}"
        self.write_text(count_text, 0, 100)
        
        # Show all files with selection indicator
        if items:
            # Default to first window
            self.show_menu_window(title, items, selected_idx, 0)
        else:
            self.write_text("No files found", 2, 0)
    
    def show_menu_window(self, title, items, selected_idx, start_idx):
        """Display a menu with a fixed window start index to avoid scrolling jitter"""
        # Header
        self.clear_line(0)
        self.write_text(title, 0, 0)
        count_text = f"{selected_idx + 1}/{len(items)}"
        self.write_text(count_text, 0, 100)
        
        # Items (lines 1..8) - use more of the OLED screen
        end_idx = min(start_idx + 8, len(items))
        for line in range(1, 9):
            self.clear_line(line)
        # Ensure we have valid bounds
        if start_idx < 0 or start_idx >= len(items):
            return
        
        for i in range(start_idx, end_idx):
            display_line = i - start_idx + 1
            
            # Multiple safety checks
            if i >= len(items) or display_line < 1 or display_line > 8:
                continue
                
            try:
                filename = items[i].split('/')[-1]
                if i == selected_idx:
                    self.write_text(f"* {filename[:16]}", display_line, 0)
                else:
                    self.write_text(f"  {filename[:16]}", display_line, 0)
            except (IndexError, AttributeError):
                # Skip malformed entries
                continue
    
    def show_status(self, line1, line2, line3=None, line4=None):
        """Show status information on multiple lines"""
        self.clear()
        self.write_text(line1, 0, 0)
        self.write_text(line2, 1, 0)
        if line3:
            self.write_text(line3, 2, 0)
        if line4:
            self.write_text(line4, 3, 0)
    
    def update_menu_selection_window(self, items, old_idx, new_idx, start_idx):
        """Update only the selection marker within a fixed window and update counter"""
        if not items:
            return
        
        # Update the counter in the top right
        self.clear_line(0)
        self.write_text("TASKUN V1", 0, 0)
        count_text = f"{new_idx + 1}/{len(items)}"
        self.write_text(count_text, 0, 100)
        
        end_idx = min(start_idx + 8, len(items))
        # Redraw old line without marker
        if old_idx is not None and old_idx >= start_idx and old_idx < end_idx:
            old_line = old_idx - start_idx + 1
            filename = items[old_idx].split('/')[-1]
            self.clear_line(old_line)
            self.write_text(f"  {filename[:16]}", old_line, 0)
        # Draw new line with marker
        if new_idx >= start_idx and new_idx < end_idx:
            new_line = new_idx - start_idx + 1
            filename = items[new_idx].split('/')[-1]
            self.clear_line(new_line)
            self.write_text(f"* {filename[:16]}", new_line, 0)
    
    def update_counter_only(self, selected_idx, total_items):
        """Update only the counter in the top right corner"""
        # Clear and redraw just the counter area
        self.set_position(0, 90)  # Position for counter
        self.write_data_bulk([0x00] * 38)  # Clear counter area
        count_text = f"{selected_idx + 1}/{total_items}"
        self.write_text(count_text, 0, 100)
    
    def move_selection_marker(self, items, old_line, new_line, start_idx):
        """Efficiently move the selection marker from old_line to new_line"""
        if not items or old_line < 1 or old_line > 8 or new_line < 1 or new_line > 8:
            return
        
        # Calculate the actual item indices
        old_item_idx = start_idx + old_line - 1
        new_item_idx = start_idx + new_line - 1
        
        # Enhanced safety checks
        if (old_item_idx < 0 or old_item_idx >= len(items) or 
            new_item_idx < 0 or new_item_idx >= len(items)):
            return
        
        # Redraw old line without asterisk
        try:
            filename = items[old_item_idx].split('/')[-1]
            self.clear_line(old_line)
            self.write_text(f"  {filename[:16]}", old_line, 0)
        except (IndexError, AttributeError):
            pass
        
        # Redraw new line with asterisk
        try:
            filename = items[new_item_idx].split('/')[-1]
            self.clear_line(new_line)
            self.write_text(f"* {filename[:16]}", new_line, 0)
        except (IndexError, AttributeError):
            pass
    
    def close(self):
        """Close the I2C bus"""
        self.bus.close()

# Example usage
if __name__ == "__main__":
    try:
        # Create display instance
        display = ImprovedOLEDDisplay()
        
        # Test menu display
        display.show_menu("TASKUN V1", ["test1.r08", "test2.r08", "test3.r08"], 1, 3)
        time.sleep(3)
        
        # Test status display
        display.show_status("PLAYING:", "test1.r08", "LATCHES: 1500", "PRESS B TO STOP")
        time.sleep(3)
        
        # Clear and close
        display.clear()
        display.close()
        
    except Exception as e:
        print(f"Error: {e}")
