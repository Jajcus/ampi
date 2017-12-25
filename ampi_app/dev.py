"""Device monitoring."""

import logging

import gi
gi.require_version('GUdev', '1.0')
from gi.repository import GUdev

logger = logging.getLogger("dev")

class InterfaceMonitor:
    def __init__(self, callback=None):
        self.client = GUdev.Client(subsystems=["sound"])
        self.callback = callback
        self.client.connect("uevent", self.uevent)

    def uevent(self, client, action, device):
        logger.debug("uevent(%r, %r, %r)", client, action, device)
        name = device.get_name()
        bus = device.get_property("ID_BUS")
        if name.startswith("card") and bus == "usb":
            if action in ("add", "change"):
                logger.info("USB interface added")
                if self.callback:
                    self.callback(True)
            elif action == "remove":
                logger.info("USB interface removed")
                if self.callback:
                    self.callback(False)

    def is_present(self, **kwargs):
        for device in self.client.query_by_subsystem("sound"):
            name = device.get_name()
            bus = device.get_property("ID_BUS")
            if name.startswith("card") and bus == "usb":
                return True
        return False
