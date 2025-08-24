#!/bin/bash

# Script to set up automatic startup of taskun_r08.py on boot

echo "Setting up taskun service..."

# Copy the service file to systemd directory
sudo cp /home/pi/taskun/taskun.service /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable taskun.service

# Start the service now (optional - for testing)
sudo systemctl start taskun.service

# Check the status
sudo systemctl status taskun.service

echo ""
echo "Setup complete! The script will now run automatically on boot."
echo ""
echo "Useful commands:"
echo "  Check status:  sudo systemctl status taskun.service"
echo "  View logs:     sudo journalctl -u taskun.service -f"
echo "  Stop service:  sudo systemctl stop taskun.service"
echo "  Disable:       sudo systemctl disable taskun.service"


