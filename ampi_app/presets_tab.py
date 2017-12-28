
"""Presets tab."""

import logging

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

logger = logging.getLogger("presets_tab")

class PresetsTab(Gtk.Notebook):
    def __init__(self, main_window):
        Gtk.Notebook.__init__(self)
        self.main_window = main_window

        self.set_tab_pos(Gtk.PositionType.LEFT)

        self.tabs = {}
        self.banks = {}
        self.main_window.gx_client.add_observer(self)

    def gx_connected(self, gx_client):
        banks = gx_client.api.banks()
        logger.info("Banks: %r", banks)
        self.banks = {b["name"]: b for b in banks}
        self.update_tabs()

    def gx_disconnected(self, gx_client):
        self.banks = {}
        self.update_tabs()

    def update_tabs(self):
        for name, tab in self.tabs.items():
            logger.debug("Removing tab for bank %r", name)
            self.remove(tab)
        self.tabs = {}
        for name, bank in sorted(self.banks.items()):
            logger.debug("Creating tab for bank %r", name)
            tab = Gtk.FlowBox()
            tab.set_border_width(10)
            tab.set_valign(Gtk.Align.START)
            tab.set_max_children_per_line(30)
            tab.set_selection_mode(Gtk.SelectionMode.NONE)
            self.append_page(tab, Gtk.Label(name))
            self.tabs[name] = tab
            for preset in bank["presets"]:
                button = Gtk.Button.new_with_label(preset)
                tab.add(button)
        self.show_all()

