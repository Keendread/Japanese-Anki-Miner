# System tray icon and menus for JAM
# Runs the app as a background process in Windows system tray

import os
import sys
import threading
import pystray
import logging
from PIL import Image, ImageDraw
from typing import Callable, Optional

class TrayManager:
    """
    Manages system tray icon, menus, and app lifecycle.
    
    Usage:
        tray = TrayManager(
            on_show_settings=show_settings_callback,
            on_quit=quit_callback,
        )
        tray.run()
    """
    
    def __init__(
        self,
        on_show_settings: Optional[Callable] = None,
        on_open_logs: Optional[Callable] = None,
        on_quit: Optional[Callable] = None,
    ):
        self.on_show_settings = on_show_settings or (lambda: None)
        self.on_open_logs = on_open_logs or (lambda: None)
        self.on_quit = on_quit or (lambda: None)
        self.icon: Optional[pystray.Icon] = None
        self.is_running = False
        
    def _create_icon(self) -> Image.Image:
        """
        Creates a simple JAM icon (can be replaced with actual logo).
        For now: creates a green square with white "JAM" text.
        """
        size = 64
        img = Image.new("RGB", (size, size), color="#1a3a1a")  # Dark green
        draw = ImageDraw.Draw(img)
        
        # Draw a white border
        border = 2
        draw.rectangle(
            [(border, border), (size - border, size - border)],
            outline="#6bff6b",  # Bright green
            width=2
        )
        
        # Try to draw "JAM" text
        try:
            # Use default font (small size)
            text = "JAM"
            # Estimate text position for centering
            draw.text((18, 22), text, fill="#6bff6b")
        except Exception:
            # If text fails, just draw a dot in the center
            draw.ellipse(
                [(28, 28), (36, 36)],
                fill="#6bff6b"
            )
        
        return img
    
    def _create_menu(self) -> pystray.Menu:
        """Creates the right-click context menu."""
        return pystray.Menu(
            pystray.MenuItem(
                "Settings",
                self._on_settings,
                default=True,  # Double-click = settings
            ),
            pystray.MenuItem(
                "View Logs",
                self._on_logs,
            ),
            pystray.MenuItem(
                "Exit",
                self._on_quit,
            ),
        )
    
    def _on_settings(self, icon, item):
        """Called when 'Settings' is clicked."""
        logging.info("[Tray] Settings menu clicked - invoking callback")
        try:
            self.on_show_settings()
            logging.info("[Tray] Settings callback executed successfully")
        except Exception as e:
            logging.error(f"[Tray] Settings callback failed: {e}", exc_info=True)
    
    def _on_logs(self, icon, item):
        """Called when 'View Logs' is clicked."""
        logging.info("[Tray] View Logs menu clicked - invoking callback")
        try:
            self.on_open_logs()
            logging.info("[Tray] Logs callback executed successfully")
        except Exception as e:
            logging.error(f"[Tray] Logs callback failed: {e}", exc_info=True)
    
    def _on_quit(self, icon, item):
        """Called when 'Exit' is clicked."""
        logging.info("[Tray] Exit menu clicked - invoking callback")
        print("[Tray] User requested exit.")
        try:
            self.is_running = False
            self.on_quit()
            logging.info("[Tray] Quit callback executed successfully")
        except Exception as e:
            logging.error(f"[Tray] Quit callback failed: {e}", exc_info=True)
        
        if self.icon:
            # Schedule stop in a separate thread to avoid blocking pystray event loop
            def _stop_icon():
                import time
                time.sleep(0.1)  # Give callback time to return
                if self.icon:
                    self.icon.stop()
            threading.Thread(target=_stop_icon, daemon=True).start()
    
    def run(self):
        """
        Starts the system tray icon (blocking).
        Run this in main thread, or in a separate thread if you need
        other work to continue.
        """
        self.is_running = True
        icon_img = self._create_icon()
        menu = self._create_menu()
        
        self.icon = pystray.Icon(
            name="JAM",
            icon=icon_img,
            title="Japanese Anki Miner",
            menu=menu,
        )
        
        print("[Tray] System tray icon started.")
        logging.info("[Tray] System tray icon started with context menu")
        self.icon.run()
    
    def stop(self):
        """Stops the tray icon."""
        if self.icon:
            self.is_running = False
            self.icon.stop()

    def notify(self, title: str, message: str, duration: int = 5000):
        """Show a tray notification if supported."""
        if not self.icon:
            return
        try:
            self.icon.notify(message, title)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
            except Exception as e:
                print(f"[Tray] Notification failed: {e}")

