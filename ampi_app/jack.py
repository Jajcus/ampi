"""Jack client, to handle jack connections."""

import logging
from collections import defaultdict
import jack
import time

from gi.repository import GObject

logger = logging.getLogger("jack")

WIRING = [
        ("Mono R", [
            ("audio", "system:capture_1", "gx_head_amp:in_0"),
            ("audio", "system:capture_2", None),
            ("audio", "gx_head_fx:out_0", "system:playback_2"),
            ("audio", "gx_head_fx:out_1", "system:playback_2"),
            ("audio", None, "system:playback_1"),
            ]),
        ("Stereo", [
            ("audio", "system:capture_1", "gx_head_amp:in_0"),
            ("audio", "system:capture_2", None),
            ("audio", "gx_head_fx:out_0", "system:playback_1"),
            ("audio", "gx_head_fx:out_1", "system:playback_2"),
            ]),
        ]

class JackClient:
    def __init__(self):
        self.jack = None
        self.wiring = None
        self.source_wiring = {}
        self.sink_wiring = {}
        self.xruns = 0
        self.skipped_xruns = 0
        self.last_xrun = 0
        self.last_xrun_log = 0
        self._load_wiring(WIRING[0])

    def _load_wiring(self, wiring):
        name, connections = wiring
        source_wiring = defaultdict(set)
        sink_wiring = defaultdict(set)
        for c_type, s_port, d_port in connections:
            if s_port:
                if d_port:
                    source_wiring[c_type, s_port].add(d_port)
                else:
                    source_wiring[c_type, s_port] = {}
            if d_port:
                if s_port:
                    sink_wiring[c_type, d_port].add(s_port)
                else:
                    sink_wiring[c_type, d_port] = {}
        self.wiring = name
        self.source_wiring = source_wiring
        self.sink_wiring = sink_wiring
        if self.jack:
            self.apply_wiring()

    def connect(self):
        if self.jack:
            return
        logger.info("Connecting to Jack...")
        try:
            self.jack = jack.Client("ampi_app")
        except jack.JackError as err:
            logger.error("Cannot connect to Jack: %s", err)
            return
        try:
            self.jack.set_port_registration_callback(self._port_registered_cb)
            self.jack.set_xrun_callback(self._xrun_cb)
            logger.info("Activating Jack...")
            self.jack.activate()
        except jack.JackError as err:
            logger.error("Cannot activate Jack client: %s", err)
            self.jack.close()
            self.jack = None
            return
        logger.info("Jack connection ready.")
        self.apply_wiring()

    def _port_registered_cb(self, port, registered):
        GObject.timeout_add(10, self._port_registered, port, registered)

    def _xrun_cb(self, delayed):
        self.xruns += 1
        now = time.monotonic()
        if self.last_xrun_log:
            if not self.last_xrun_log or now - self.last_xrun_log > 2:
                if self.skipped_xruns > 0:
                    logger.warning("%i xruns!", self.skipped_xruns + 1)
                else:
                    logger.warning("xruns!")
                self.skipped_xruns = 0
                self.last_xrun_log = now
            else:
                self.skipped_xruns += 1
        else:
            logger.warning("xrun!")
        self.last_xrun = now

    def _port_registered(self, port, registered):
        if not registered:
            logger.debug("Jack port %r unregistered", port.name)
            return
        logger.debug("Jack port %r registered", port.name)
        if port.is_output:
            self._connect_source(port)
        elif port.is_input:
            self._connect_sink(port)

    def _connect_source(self, port):
        if port.is_audio:
            p_type = "audio"
        elif port.is_midi:
            p_type = "midi"
        else:
            logger.debug("Unknown jack port type: %r", port)
            return
        if (p_type, port.name) not in self.source_wiring:
            logger.debug("No connection rules for source port %r,%r", p_type, port)
            return
        destinations = self.source_wiring[p_type, port.name]
        try:
            connections = [p.name for p in self.jack.get_all_connections(port)]
        except jack.JackError as err:
            logger.warning("get_all_connections(%r): %s", port, err)
            return
        logger.debug("%s: destinations: %r, connections: %r", port.name, destinations, connections)
        for conn in connections:
            if conn not in destinations:
                logger.info("Disconnecting %r from %r", port.name, conn)
                try:
                    self.jack.disconnect(port, conn)
                except jack.JackError as err:
                    logger.warning("Cannot disconnect %r from %r: %s",
                                   port.name, conn, err)
        for dest in destinations:
            if dest not in connections:
                try:
                    d_port = self.jack.get_port_by_name(dest)
                except jack.JackError as err:
                    logger.debug("%s: %s", dest, err)
                    continue
                logger.info("Connecting %r to %r", port.name, d_port.name)
                try:
                    self.jack.connect(port, d_port)
                except jack.JackError as err:
                    logger.warning("Cannot connect %r to %r: %s",
                                   port.name, d_port.name, err)

    def _connect_sink(self, port):
        if port.is_audio:
            p_type = "audio"
        elif port.is_midi:
            p_type = "midi"
        else:
            logger.debug("Unknown jack port type: %r", port)
            return
        if (p_type, port.name) not in self.sink_wiring:
            logger.debug("No connection rules for sink port %r,%r", p_type, port)
            return
        sources = self.sink_wiring[p_type, port.name]
        try:
            connections = [p.name for p in self.jack.get_all_connections(port)]
        except jack.JackError as err:
            logger.warning("get_all_connections(%r): %s", port, err)
            return
        logger.debug("%s: sources: %r, connections: %r", port.name, sources, connections)
        for conn in connections:
            if conn not in sources:
                logger.info("Disconnecting %r from %r", conn, port.name)
                try:
                    self.jack.disconnect(conn, port)
                except jack.JackError as err:
                    logger.warning("Cannot disconnect %r from %r: %s",
                                   conn, port.name, err)
        for src in sources:
            if src not in connections:
                try:
                    s_port = self.jack.get_port_by_name(src)
                except jack.JackError as err:
                    logger.debug("%s: %s", src, err)
                    continue
                logger.info("Connecting %r to %r", src, port.name)
                try:
                    self.jack.connect(src, port)
                except jack.JackError as err:
                    logger.warning("Cannot connect %r to %r: %s",
                                   src, port.name, err)

    def apply_wiring(self):
        if not self.jack:
            return
        logger.info("Connecting Jack wires...")
        logger.debug("source_wiring: %r", self.source_wiring)

        for port in self.jack.get_ports(is_output=True):
            self._connect_source(port)
        for port in self.jack.get_ports(is_input=True):
            self._connect_sink(port)

    def get_wirings(self):
        return [name for name, connections in WIRING]

    def load_wiring(self, name):
        for wiring in WIRING:
            if wiring[0] == name:
                return self._load_wiring(wiring)
        raise KeyError(name)

    def get_status_string(self):
        if not self.jack:
            return "<span foreground='#800000'>disconnected</span>"
        status_s = "<span foreground='#008000'>connected</span>, "
        try:
            load = self.jack.cpu_load()
            if load <= 80:
                color = "#008000"
            else:
                color = "#800000"
            status_s += "<span foreground='{}'>{:3.0f}% CPU load</span>, ".format(color, load)
        except jack.JackError as err:
            logger.warning("cpu_load: %s", err)
            status_s += "unknown CPU load, "
        if not self.xruns:
            color = "#008000"
            xrun_s = "0 xruns"
        else:
            now = time.monotonic()
            since_last_xrun = int(now - self.last_xrun)
            if since_last_xrun < 120:
                delta_s = "{:3d}s".format(since_last_xrun)
                color = "#800000"
            else:
                delta_s = "{:d}m".format(since_last_xrun // 60)
                color = "#008000"
            xrun_s = "{} xruns (last {} ago)".format(self.xruns, delta_s)
        status_s += "<span foreground='{}'>{}</span> ".format(color, xrun_s)
        return status_s
