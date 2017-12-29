
"""Presets tab."""

import logging

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

logger = logging.getLogger("presets_tab")

def get_value(params, name):
    return params.get(name, {}).get("value", "{}").get(name)

class PresetsTab(Gtk.Notebook):
    def __init__(self, main_window):
        Gtk.Notebook.__init__(self)
        self.main_window = main_window

        self.set_tab_pos(Gtk.PositionType.LEFT)

        self.tabs = {}
        self.banks = {}
        self.current_banke = None
        self.current_preset = None
        self.main_window.gx_client.add_observer(self)

    def gx_connected(self, gx_client):
        params = gx_client.api.get_parameter("system.current_bank",
                                             "system.current_preset")
        self.current_bank = get_value(params, "system.current_bank")
        self.current_preset = get_value(params, "system.current_preset")
        logger.info("Current preset: %r, %r", self.current_bank, self.current_preset)
        banks = gx_client.api.banks()
        logger.info("Banks: %r", banks)
        self.banks = {b["name"]: b for b in banks}
        self.update_tabs()

    def gx_disconnected(self, gx_client):
        self.banks = {}
        self.update_tabs()

    def gx_preset_changed(self, gx_client, bank_name, preset_name):
        logger.info("Preset changed to: %r, %r", bank_name, preset_name)
        button = self.buttons.get((bank_name, preset_name))
        if not button:
            logging.warning("No preset button for %, %r", bank_name, preset_name)
        elif not button.get_active():
            button.set_active(True)
        tab_num = self.tabs.get(bank_name, [0, None])[0]
        self.set_current_page(tab_num)
        self.current_bank = bank_name
        self.current_preset = preset_name

    def _button_toggled(self, button, bank_name, preset_name):
        logger.debug("Button toggled: %r: %r, %r", button, bank_name, preset_name)
        if not button.get_active():
            return
        if bank_name == self.current_bank and preset_name == self.current_preset:
            return
        self.current_bank = bank_name
        self.current_preset = preset_name
        logger.info("Loading preset: %r, %r", bank_name, preset_name)
        self.main_window.gx_client.api.setpreset(bank_name, preset_name)

    def update_tabs(self):
        for name, tabinfo in self.tabs.items():
            logger.debug("Removing tab for bank %r", name)
            self.remove(tabinfo[1])
        self.tabs = {}
        self.buttons = {}
        button = None
        for bank_name, bank in sorted(self.banks.items()):
            logger.debug("Creating tab for bank %r", bank_name)
            tab = Gtk.ScrolledWindow()
            tab.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            box = Gtk.FlowBox()
            box.set_border_width(10)
            box.set_valign(Gtk.Align.START)
            box.set_max_children_per_line(30)
            box.set_selection_mode(Gtk.SelectionMode.NONE)
            tab.add(box)
            tab_num = self.append_page(tab, Gtk.Label(bank_name))
            if bank_name == self.current_bank:
                tab.show()
                self.set_current_page(tab_num)
            self.tabs[bank_name] = (tab_num, tab)
            for preset in bank["presets"]:
                button = Gtk.RadioButton.new_with_label_from_widget(button, preset)
                button.set_mode(False)
                button.set_size_request(80, 80)
                if bank_name == self.current_bank and preset == self.current_preset:
                    button.set_active(True)
                button.connect("toggled", self._button_toggled, bank_name, preset)
                box.add(button)
                self.buttons[bank_name, preset] = button
        self.show_all()

