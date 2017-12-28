
"""Status tab."""

import logging

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

logger = logging.getLogger("status_tab")

class StatusTab(Gtk.Box):
    def __init__(self, main_window):
        Gtk.Box.__init__(self)
        self.main_window = main_window

        self.set_orientation(Gtk.Orientation.VERTICAL)
        self.set_border_width(10)

        self.iface_status_l = Gtk.Label('USB interface status: unknown')

        self.jackd_status_l = Gtk.Label('Jack server status: unknown')
        self.jackd_status_l.set_justify(Gtk.Justification.LEFT)
        self.pack_start(self.jackd_status_l, False, True, 2)

        self.gx_status_l = Gtk.Label('Guitarix status: unknown')
        self.gx_status_l.set_justify(Gtk.Justification.LEFT)
        self.pack_start(self.gx_status_l, False, True, 2)

        self.log_sw = Gtk.ScrolledWindow()
        self.log_sw.set_border_width(10)
        self.log_sw.set_hexpand(True)
        self.log_sw.set_vexpand(True)

        self.log_w = Gtk.TextView()
        self.log_w.set_editable(False)
        self.log_w.set_cursor_visible(False)
        self.log_b = self.log_w.get_buffer()
        self.log_b.connect("changed", self.log_b_changed_cb)

        self.log_sw.add(self.log_w)
        self.pack_start(self.log_sw, True, True, 2)

    def update_iface_status(self, present):
        if present:
            self.iface_status_l.set_markup("USB interface status: "
                    "<span foreground='#008000'>present</span>")
        else:
            self.iface_status_l.set_markup("USB interface status: "
                    "<span foreground='#800000'>absent</span>")

    def update_jackd_status(self, started):
        if started:
            self.jackd_status_l.set_markup("Jack server status: "
                    "<span foreground='#008000'>started</span>")
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
