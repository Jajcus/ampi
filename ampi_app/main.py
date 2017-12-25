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
        self.jack_client = None
        self.create_widgets()
        log_handler = TextBufferHandler(self.log_b)
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
        self.gx_nanny = Nanny("guitarix", ["/usr/bin/guitarix"],
                                kill_list=["guitarix"],
                                callback=self.update_gx_status)

        self.update_jackd_status(False)
        self.update_gx_status(False)
        self.jack_client = JackClient()
        self.update_iface_status(self.iface_monitor.is_present())

    def quit(self, widget, event):
        self.gx_nanny.stop()
        self.jack_nanny.stop()
        Gtk.main_quit()

    def create_widgets(self):
        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        self.status_p = Gtk.Box()
        self.status_p.set_orientation(Gtk.Orientation.VERTICAL)
        self.status_p.set_border_width(10)

        self.iface_status_l = Gtk.Label('USB interface status: unknown')
        self.iface_status_l.set_justify(Gtk.Justification.LEFT)
        self.status_p.pack_start(self.iface_status_l, False, True, 2)

        self.jackd_status_l = Gtk.Label('Jack server status: unknown')
        self.jackd_status_l.set_justify(Gtk.Justification.LEFT)
        self.status_p.pack_start(self.jackd_status_l, False, True, 2)

        self.gx_status_l = Gtk.Label('Guitarix status: unknown')
        self.gx_status_l.set_justify(Gtk.Justification.LEFT)
        self.status_p.pack_start(self.gx_status_l, False, True, 2)

        self.log_sw = Gtk.ScrolledWindow()
        self.log_sw.set_border_width(10)
        self.log_sw.set_hexpand(True)
        self.log_sw.set_vexpand(True)

        self.log_w = Gtk.TextView()
        self.log_w.set_editable(False)
        self.log_w.set_cursor_visible(False)
        self.log_b = self.log_w.get_buffer()
        self.log_b.connect("changed", self.log_b_changed_cb)

        log_i = self.log_b.get_start_iter()

        self.log_sw.add(self.log_w)
        self.status_p.pack_start(self.log_sw, True, True, 2)

        self.notebook.append_page(self.status_p, Gtk.Label('Status'))

    def update_iface_status(self, present):
        if present:
            self.iface_status_l.set_markup("USB interface status: "
                    "<span foreground='#008000'>present</span>")
            GObject.timeout_add(1000, self.jack_nanny.start)
        else:
            self.iface_status_l.set_markup("USB interface status: "
                    "<span foreground='#800000'>absent</span>")
            self.gx_nanny.stop()
            self.jack_nanny.stop()

    def update_jackd_status(self, started):
        if started:
            self.jackd_status_l.set_markup("Jack server status: "
                    "<span foreground='#008000'>started</span>")
            GObject.timeout_add(1000, self.gx_nanny.start)
            GObject.timeout_add(1000, self.jack_client.connect)
        else:
            self.jackd_status_l.set_markup("Jack server status: "
                    "<span foreground='#800000'>stopped</span>")

    def update_gx_status(self, started):
        if started:
            self.gx_status_l.set_markup("Guitarix status: "
                    "<span foreground='#008000'>started</span>")
        else:
            self.gx_status_l.set_markup("Guitarix status: "
                    "<span foreground='#800000'>stopped</span>")

    def log_b_changed_cb(self, data):
        log_w_end = self.log_w.props.vadjustment.get_upper() - self.log_w.props.vadjustment.get_page_size()
        self.log_w.props.vadjustment.set_value(log_w_end)

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
