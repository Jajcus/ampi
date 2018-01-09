#!/usr/bin/python

import configparser
import os
import logging
import argparse
import signal

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from .dev import InterfaceMonitor
from .proc import Nanny
from .jack import JackClient
from .guitarix import GuitarixClient
from .status_tab import StatusTab
from .presets_tab import PresetsTab
from .tracks_tab import TracksTab
from .system_tab import SystemTab

logger = logging.getLogger("main")

LOG_COLORS = [
        (logging.DEBUG, "#505050"),
        (logging.INFO, "#101010"),
        (logging.WARNING, "#c06000"),
        (logging.ERROR, "#c00000"),
        (logging.CRITICAL, "#ff0000"),
        ]

class TextBufferHandler(logging.Handler):
    """
    A logging handler class which writes logging records to a Gtk text buffer.
    """
    def __init__(self, text_buffer):
        logging.Handler.__init__(self)
        self.buffer = text_buffer
        self.text_tags = {}

    def _get_tag(self, level):
        tag = self.text_tags.get(level)
        if tag:
            return tag
        for i in range(len(LOG_COLORS) - 1):
            if level < LOG_COLORS[i + 1][0]:
                color = LOG_COLORS[i][1]
                break
        else:
            color = LOG_COLORS[-1][1]
        tag = self.buffer.create_tag("log_level_{}".format(level),
                                     foreground=color)
        self.text_tags[level] = tag
        return tag

    def emit(self, record):
        """
        Emit a record.
        """
        try:
            msg = self.format(record)
            level = record.levelno
            def add_line():
                tag = self._get_tag(level)
                buf_iter = self.buffer.get_end_iter()
                self.buffer.insert_with_tags(buf_iter, msg + "\n", tag)
            GLib.idle_add(add_line)
        except Exception:
            self.handleError(record)

class MainWindow(Gtk.Window):

    def __init__(self, args):
        self.config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        pkg_dir = os.path.dirname(__file__)
        conf_dir = os.path.expanduser("~/.config/ampi_app")
        self.config.read([os.path.join(pkg_dir, "config"), os.path.join(conf_dir, "config")],
                         encoding='utf-8')
        Gtk.Window.__init__(self, title="Ampi")

        self.set_default_size(self.config["UI"].getint("width"),
                              self.config["UI"].getint("height"))
        self.connect("delete-event", self.quit)

        self.jack_nanny = None
        self.gx_nanny = None

        self.jack_client = JackClient()
        self._gx_start_id = None
        self.gx_client = GuitarixClient(self.config["Guitarix"]["rpc_host"],
                                        int(self.config["Guitarix"]["rpc_port"]))

        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, self._signal, "SIGTERM")
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGHUP, self._signal, "SIGHUP")
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, self._signal, "SIGINT")

        self.notebook = Gtk.Notebook()
        self.add(self.notebook)
        self.status_tab = StatusTab(self)
        self.notebook.append_page(self.status_tab, Gtk.Label('Status'))
        self.presets_tab = PresetsTab(self)
        self.notebook.append_page(self.presets_tab, Gtk.Label('Presets'))
        self.tracks_tab = TracksTab(self)
        self.notebook.append_page(self.tracks_tab, Gtk.Label('Tracks'))
        self.system_tab = SystemTab(self)
        self.notebook.append_page(self.system_tab, Gtk.Label('System'))
        self.notebook.show_all()
        self.notebook.set_current_page(0)

        log_handler = TextBufferHandler(self.status_tab.log_b)
        log_handler.setFormatter(logging.Formatter())
        root_logger = logging.getLogger()
        root_logger.addHandler(log_handler)
        if args.debug:
            root_logger.setLevel(logging.DEBUG)
        else:
            root_logger.setLevel(logging.INFO)
        self.iface_monitor = InterfaceMonitor(self.update_iface_status)

        jack_cmd = self.config["Jack"]["cmdline"].split()
        jack_name = os.path.basename(jack_cmd[0])

        self.jack_nanny = Nanny(jack_name, jack_cmd,
                                kill_list=["jackd", "jackdbus", "qjackctl"],
                                callback=self.update_jackd_proc_status)

        gx_cmd = self.config["Guitarix"]["cmdline"].split()
        self.gx_nanny = Nanny("guitarix", gx_cmd,
                                kill_list=["guitarix"],
                                callback=self.update_gx_proc_status)

        self.update_jackd_proc_status(False)
        self.update_gx_proc_status(False)
        self.gx_client.add_observer(self, "all")
        self.gx_client.add_observer(self.status_tab, "state")
        self.update_iface_status(self.iface_monitor.is_present())
        if not self.config["Jack"].getboolean("wait_for_device"):
            GLib.timeout_add(1000, self.jack_nanny.start)

    def _signal(self, signum):
        logger.info("Exitting with signal: %r", signum)
        self.quit()

    def quit(self, *args):
        if self.gx_nanny:
            self.gx_nanny.let_it_stop()
        if self.gx_client:
            GLib.idle_add(self.gx_client.api.shutdown)
        if self.tracks_tab:
            self.tracks_tab.stop_player()
        GLib.timeout_add(2000, self._do_quit)

    def _do_quit(self):
        if self.gx_nanny:
            self.gx_nanny.stop()
        if self.jack_nanny:
            self.jack_nanny.stop()
        Gtk.main_quit()

    def update_iface_status(self, present):
        self.status_tab.update_iface_status(present)
        if present:
            GLib.timeout_add(1000, self.jack_nanny.start)
        else:
            self.gx_nanny.stop()
            self.jack_nanny.stop()

    def update_jackd_proc_status(self, started):
        self.status_tab.update_jackd_proc_status(started)
        self.tracks_tab.update_jackd_proc_status(started)
        if started:
            GLib.timeout_add(1000, self.gx_nanny.start)
            GLib.timeout_add(1000, self.jack_client.connect)

    def update_gx_proc_status(self, started):
        self.status_tab.update_gx_proc_status(started)
        if started:
            self._gx_start_id = GLib.timeout_add(1000, self.gx_client.connect)
        else:
            if self._gx_start_id is not None:
                GLib.source_remove(self._gx_start_id)
                self._gx_start_id = None

    def gx_connected(self, gx_client):
        if self._gx_start_id is not None:
            # if connected, then the connect function returned None
            # and thhis has already been removed from glib
            self._gx_start_id = None

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
