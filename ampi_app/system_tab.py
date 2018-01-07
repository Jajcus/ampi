
"""System tab."""

import logging
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

logger = logging.getLogger("system_tab")

class SystemTab(Gtk.FlowBox):
    def __init__(self, main_window):
        Gtk.FlowBox.__init__(self,
                             border_width=10,
                             valign=Gtk.Align.START,
                             max_children_per_line=30,
                             selection_mode=Gtk.SelectionMode.NONE)
        self.main_window = main_window

        for name, command in self.main_window.config["System"].items():
            button = Gtk.Button.new_with_label(name)
            button.connect("clicked", self._button_clicked, name, command)
            self.add(button)

    def _button_clicked(self, button, name, command):
        logger.debug("Button clicked: %r: %r, %r", button, name, command)
        try:
            output = subprocess.check_output(command,
                                             shell=True,
                                             stderr=subprocess.STDOUT)
        except OSError as err:
            logger.error("Could not exec %r: %s", command, err)
        except subprocess.CalledProcessError as err:
            logger.error("%r failed: %s", command, err)
            for line in err.output.decode(errors="replace").split("\n"):
                logger.error(line)
