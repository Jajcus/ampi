
"""Status tab."""

import logging

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

logger = logging.getLogger("status_tab")

class StatusTab(Gtk.Box):
    def __init__(self, main_window):
        Gtk.Box.__init__(self)
        self.main_window = main_window

        self.set_orientation(Gtk.Orientation.VERTICAL)

        grid = Gtk.Grid(border_width=10,
                        column_spacing=5)
        label = Gtk.Label("USB interface:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 0, 1, 1)
        self.iface_status_l = Gtk.Label('unknown',
                                        justify=Gtk.Justification.LEFT,
                                        xalign=0)
        grid.attach(self.iface_status_l, 1, 0, 1, 1)

        label = Gtk.Label("Jackd process:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 1, 1, 1)
        self.jackd_proc_l = Gtk.Label('unknown',
                                      justify=Gtk.Justification.LEFT,
                                      xalign=0)
        grid.attach(self.jackd_proc_l, 1, 1, 1, 1)

        label = Gtk.Label("Jack status:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 2, 1, 1)
        self.jack_status_l = Gtk.Label('unknown',
                                       justify=Gtk.Justification.LEFT,
                                       xalign=0)
        grid.attach(self.jack_status_l, 1, 2, 1, 1)

        label = Gtk.Label("Guitarix process:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 3, 1, 1)
        self.gx_proc_l = Gtk.Label('unknown',
                                   justify=Gtk.Justification.LEFT,
                                   xalign=0)
        grid.attach(self.gx_proc_l, 1, 3, 1, 1)

        label = Gtk.Label("Guitarix status:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 4, 1, 1)
        self.gx_status_l = Gtk.Label('unknown',
                                     justify=Gtk.Justification.LEFT,
                                     xalign=0)
        grid.attach(self.gx_status_l, 1, 4, 1, 1)

        self.pack_start(grid, False, False, 2)

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

        GLib.timeout_add(2000, self.update_jack_status)

    def update_iface_status(self, present):
        if present:
            self.iface_status_l.set_markup("<span foreground='#008000'>present</span>")
        else:
            self.iface_status_l.set_markup("<span foreground='#800000'>absent</span>")

    def update_jackd_proc_status(self, started):
        if started:
            self.jackd_proc_l.set_markup("<span foreground='#008000'>started</span>")
        else:
            self.jackd_proc_l.set_markup("<span foreground='#800000'>stopped</span>")
            self.jack_status_l.set_markup("<span foreground='#800000'>disconnected</span>")

    def update_gx_proc_status(self, started):
        if started:
            self.gx_proc_l.set_markup("<span foreground='#008000'>started</span>")
        else:
            self.gx_proc_l.set_markup("<span foreground='#800000'>stopped</span>")
            self.gx_status_l.set_markup("<span foreground='#800000'>disconnected</span>")

    def update_jack_status(self):
        status_str = self.main_window.jack_client.get_status_string()
        self.jack_status_l.set_markup(status_str)
        return True

    def update_gx_status(self, color, status_str):
        self.gx_status_l.set_markup("<span foreground='{}'>{}</span>".format(color, status_str))

    def gx_connected(self, gx_client):
        state = gx_client.api.getstate()
        self.update_gx_status("#008000", state)

    def gx_state_changed(self, gx_client, state):
        self.update_gx_status("#008000", state)

    def gx_disconnected(self, gx_client):
        self.update_gx_status("#800000", "disconnected")

    def log_b_changed_cb(self, data):
        log_w_end = self.log_w.props.vadjustment.get_upper() - self.log_w.props.vadjustment.get_page_size()
        self.log_w.props.vadjustment.set_value(log_w_end)

