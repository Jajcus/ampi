
"""Tracks tab."""

import os
import glob
import logging
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

from .proc import Nanny

TRACKS_DIR = os.path.expanduser("~/.config/ampi_app/tracks")

logger = logging.getLogger("tracks_tab")

class TracksTab(Gtk.Box):
    def __init__(self, main_window):
        Gtk.Box.__init__(self)
        self.main_window = main_window

        player_cmd = main_window.config["Tracks"]["player_cmdline"].split()
        player_name = os.path.basename(player_cmd[0])
        self.player_nanny = Nanny(player_name, player_cmd,
                                  callback=self._update_player_status,
                                  stdout_callback=self._mplayer_output,
                                  input_pipe=True)

        self.set_orientation(Gtk.Orientation.VERTICAL)

        self.track_title_l = Gtk.Label("-- no track --",
                                       justify=Gtk.Justification.CENTER,
                                       xalign=0.5)
        self.pack_start(self.track_title_l, False, False, 2)

        grid = Gtk.Grid(border_width=10,
                        column_spacing=5,
                        hexpand=True)

        label = Gtk.Label("Volume:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 0, 1, 1)
        self.volume_s = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                  hexpand=True,
                                  draw_value=False)
        self.volume_s.set_range(0, 150)
        self.volume_s.set_increments(1, 10)
        self.volume_s.set_value(50)
        self.volume_s.set_round_digits(0)
        for pos in range(0, 200, 50):
            self.volume_s.add_mark(pos, Gtk.PositionType.TOP, "{}%".format(pos))
        self.volume_s.connect("value-changed", self._volume_changed)
        grid.attach(self.volume_s, 1, 0, 1, 1)

        label = Gtk.Label("Tempo:",
                          justify=Gtk.Justification.RIGHT,
                          xalign=1)
        grid.attach(label, 0, 1, 1, 1)
        self.tempo_s = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                                  hexpand=True,
                                  draw_value=False)
        self.tempo_s.set_range(25, 225)
        self.tempo_s.set_increments(5, 25)
        self.tempo_s.set_value(100)
        for pos in range(25, 250, 25):
            self.tempo_s.add_mark(pos, Gtk.PositionType.TOP, "{}%".format(pos))
        self.tempo_s.connect("value-changed", self._tempo_changed)
        grid.attach(self.tempo_s, 1, 1, 1, 1)

        self.pack_start(grid, False, False, 2)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                             halign=Gtk.Align.CENTER)
        self.play_b = Gtk.Button.new_with_label("Play")
        self.play_b.connect("clicked", self._play_clicked)
        button_box.pack_start(self.play_b, False, False, 2)
        self.stop_b = Gtk.Button.new_with_label("Stop")
        self.stop_b.connect("clicked", self._stop_clicked)
        button_box.pack_start(self.stop_b, False, False, 2)

        self.pack_start(button_box, False, False, 2)

        self.tracklist = Gtk.FlowBox(border_width=10,
                                     valign=Gtk.Align.START,
                                     max_children_per_line=30,
                                     selection_mode=Gtk.SelectionMode.NONE)
        self.pack_start(self.tracklist, True, True, 2)

        self.current_track_name = None
        self.current_track_filename = None
        self.playing = False

        self.update_tracklist()
        self._update_button_states()

    def __del__(self):
        if hasattr(self, "player_nanny"):
            self.stop_player()

    def stop_player(self):
        if self.player_nanny:
            self.player_nanny.stop()
            self.player_nanny = None

    def update_jackd_proc_status(self, started):
        if started and self.player_nanny:
            GLib.timeout_add(1000, self.player_nanny.start)
        elif self.player_nanny:
            GLib.timeout_add(1000, self.player_nanny.stop)

    def _update_player_status(self, started):
        self._update_button_states()

    def _player_command(self, *args):
        if not self.player_nanny:
            return
        command = " ".join(str(arg) for arg in args)
        if not self.playing and args[0] != "pause":
            command = "pausing " + command
        try:
            self.player_nanny.write(command + "\n")
        except OSError as err:
            logger.error("Cannot set %r command to the track player: %s",
                         command, err)

    def _load_track(self):
        self._player_command("stop")
        self.playing = False
        if self.current_track_filename:
            self._player_command("loadfile", self.current_track_filename)
            self._player_command("volume", self.volume_s.get_value(), 1)
            self._player_command("speed_set", self.tempo_s.get_value() / 100)

    def _update_button_states(self):
        if self.player_nanny.is_started() and self.current_track_name is not None:
            self.play_b.set_sensitive(True)
            self.stop_b.set_sensitive(True)
        else:
            self.play_b.set_sensitive(False)
            self.stop_b.set_sensitive(False)

    def _volume_changed(self, scale):
        self._player_command("volume", self.volume_s.get_value(), 1)

    def _tempo_changed(self, scale):
        self._player_command("speed_set", self.tempo_s.get_value() / 100.0)

    def _play_clicked(self, button):
        self.playing = not self.playing
        self._player_command("pause")

    def _stop_clicked(self, button):
        self._load_track()

    def _track_selected(self, button, track_name, track_filename):
        logger.debug("Track selected: %r: %r, %r", button, track_name, track_filename)
        self.current_track_name = track_name
        self.current_track_filename = track_filename
        self.track_title_l.set_text(track_name)
        self._update_button_states()
        if self.player_nanny.is_started():
            self._load_track()

    def _mplayer_output(self, data):
        if b"=====  PAUSE  =====" in data:
            self.playing = False
        elif b"\n\n" in data or not data.strip():
            # EOF?
            GLib.idle_add(self._load_track)

    def update_tracklist(self):
        for child in self.tracklist.get_children():
            child.destroy()

        tracks = []
        logger.debug("Searching for backing track files...")
        for filename in glob.glob(os.path.join(TRACKS_DIR, "*")):
            if not os.path.isfile(filename):
                logger.debug("Skipping %r: not a regular file")
                continue
            name = os.path.splitext(os.path.basename(filename))[0]
            name = name.replace("_", " ")
            logger.debug("Track found: %s (%s)", name, filename)
            tracks.append((name, filename))

        if not tracks:
            label = Gtk.Label("No tracks",
                              justify=Gtk.Justification.LEFT,
                              xalign=0)
            self.tracklist.add(label)
            return

        for name, filename in tracks:
            button = Gtk.Button.new_with_label(name)
            button.connect("clicked", self._track_selected, name, filename)
            self.tracklist.add(button)

        self.show_all()
