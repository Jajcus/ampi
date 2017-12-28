#!/usr/bin/python

import os
import logging
import argparse

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject, GLib

from .dev import InterfaceMonitor
from .proc import Nanny
from .jack import JackClient
from .guitarix import GuitarixClient
from .status_tab import StatusTab
from .presets_tab import PresetsTab

logger = logging.getLogger("main")

JACK_ARGS = ["-dalsa", "-dhw:1", "-r48000", "-p64", "-n3", "-I445", "-O445"]

class TextBufferHandler(logging.Handler):
    """
    A logging handler class which writes logging records to a Gtk text buffer.
    """
    def __init__(self, text_buffer):
        logging.Handler.__init__(self)
        self.buffer = text_buffer

    def emit(self, record):
        """
        Emit a record.
        """
        try:
            msg = self.format(record)
            def add_line():
                buf_iter = self.buffer.get_end_iter()
                self.buffer.insert(buf_iter, msg + "\n")
            GLib.idle_add(add_line)
        except Exception:
            self.handleError(record)

class MainWindow(Gtk.Window):

    def __init__(self, args):
        Gtk.Window.__init__(self, title="Ampi")
        self.connect("delete-event", self.quit)

        self.jack_nanny = None
        self.gx_nanny = None

        self.jack_client = JackClient()
        self.gx_client = GuitarixClient()

        self.notebook = Gtk.Notebook()
        self.add(self.notebook)
        self.status_tab = StatusTab(self)
        self.notebook.append_page(self.status_tab, Gtk.Label('Status'))
        self.presets_tab = PresetsTab(self)
        self.notebook.append_page(self.presets_tab, Gtk.Label('Presets'))

        log_handler = TextBufferHandler(self.status_tab.log_b)
        log_handler.setFormatter(logging.Formatter())
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)
        if args.debug:
            root_logger.setLevel(logging.DEBUG)
        else:
            root_logger.setLevel(logging.INFO)
        self.iface_monitor = InterfaceMonitor(self.update_iface_status)

        if os.path.exists("/usr/bin/jackd"):
            jack_name = "jackd"
            jack_cmd = ["/usr/bin/jackd"] + JACK_ARGS
        else:
            jack_name = "qjackctl"
            jack_cmd = ["/usr/bin/qjackctl"]

        self.jack_nanny = Nanny(jack_name, jack_cmd,
                                kill_list=["jackd", "jackdbus", "qjackctl"],
                                callback=self.update_jackd_status)

        gx_cmd = ["/usr/bin/guitarix",
                  "--rpchost={}".format(self.gx_client.host),
                  "--rpcport={}".format(self.gx_client.port)]
        self.gx_nanny = Nanny("guitarix", gx_cmd,
                                kill_list=["guitarix"],
                                callback=self.update_gx_status)

        self.update_jackd_status(False)
        self.update_gx_status(False)
        self.gx_client.add_observer(self, "all")
        self.update_iface_status(self.iface_monitor.is_present())

    def quit(self, widget, event):
        self.gx_nanny.stop()
        self.jack_nanny.stop()
        Gtk.main_quit()

    def update_iface_status(self, present):
        self.status_tab.update_iface_status(present)
        if present:
            GObject.timeout_add(1000, self.jack_nanny.start)
        else:
            self.gx_nanny.stop()
            self.jack_nanny.stop()

    def update_jackd_status(self, started):
        self.status_tab.update_jackd_status(started)
        if started:
            GObject.timeout_add(1000, self.gx_nanny.start)
            GObject.timeout_add(1000, self.jack_client.connect)

    def update_gx_status(self, started):
        self.status_tab.update_gx_status(started)
        if started:
            GObject.timeout_add(1000, self.gx_client.connect)

    def gx_message(self, gx_client, level, message):
        logger.info("Guitarix: %s %s", level, message)

def main():
    parser = argparse.ArgumentParser(description="Ampi UI and process management")
    parser.add_argument("-d", "--debug", action="store_true")
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    win = MainWindow(args)
    win.show_all()
    Gtk.main()

if __name__ == "__main__":
    main()
