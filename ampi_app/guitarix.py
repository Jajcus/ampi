"""Guitarix JSON-RPC client."""

import json
import threading
import random
import socket
import time
import logging

from gi.repository import GLib

from ._guitarix_methods import GuitarixMethods

logger = logging.getLogger("guitarix")

SEND_QUEUE_LEN = 100
RESULT_BUF_SIZE = 100
TIMEOUT = 10

class GuitarixClientError(Exception):
    pass

class GuitarixRPCError(GuitarixClientError):
    pass

class GuitarixClient:
    def __init__(self, host="localhost", port=9090):
        self.host = host
        self.port = port
        self.api = GuitarixMethods(self)
        self._req_id = random.randint(0, 2**30)
        self._lock = threading.RLock()
        self._thread = None
        self._observers = {}
        self._socket = None
        self._results = {}

    def add_observer(self, observer, tokens=None):
        if isinstance(tokens, str):
            tokens = {tokens}
        elif tokens:
            tokens = set(tokens)
        else:
            tokens = set()

        with self._lock:
            if observer in self._observers:
                self._observers[observer].update(tokens)
            else:
                self._observers[observer] = tokens
            if self.connected():
                if tokens:
                    self.api.listen(*tokens)
                self._call_observer(observer, "connected")

    def connected(self):
        return self._socket and self._thread

    def connect(self):
        logger.debug("Connecting to guitarix RPC")
        with self._lock:
            if self._socket and self._thread:
                return
            elif self._socket or self._thread:
                self._disconnect()
            sock = socket.socket()
            sock.settimeout(TIMEOUT)
            sock.connect((self.host, self.port))
            self._socket = sock
            self._thread = threading.Thread(name="Guitarix client",
                                           target=self._run,
                                           daemon=True)
            self._thread.start()
            for observer, tokens in self._observers.items():
                if tokens:
                    self.api.listen(*tokens)
            self._call_observers("connected")

    def disconnect(self):
        with self._lock:
            return self._disconnect()

    def _disconnect(self):
        sock = self._socket
        if sock:
            self._socket = None
            sock.close()
        thread = self._thread
        if thread and thread != threading.current_thread():
            thread.join(TIMEOUT)
        for req_id in list(self._results):
            res = self._results[req_id]
            if isinstance(res, threading.Condition):
                self._results[req_id] = GuitarixClientError("Disconnected")
                res.notify_all()
        self._call_observers("disconnected")

    def _call_observer(self, observer, event, *args):
        method_name = "gx_" + event
        method = getattr(observer, method_name, None)
        if method:
            GLib.idle_add(method, *[self] + list(args))
        else:
            logger.debug("%r has no %r method", observer, method_name)

    def _call_observers(self, event, *args):
        for observer, token in self._observers.items():
            self._call_observer(observer, event, *args)

    def _send_call(self, name, args, req_id=None):
        msg = {
                "jsonrpc": "2.0",
                "method": name,
                "params": args,
                }
        if req_id is not None:
            msg["id"] = req_id

        if not self._socket:
            logger.error("Cannot call Guitarix %s%r - disconnected", name, args)
            raise GuitarixClientError("Disconnected")

        try:
            msg_s = json.dumps(msg) + "\n"
            logger.debug("Sending: %r", msg_s)
            self._socket.send(msg_s.encode("utf-8"))
        except socket.error as err:
            raise GuitarixClientError("Socket error: {}".format(err))

    def notify(self, name, *args):
        logger.debug("%s%r notify request", name, args)
        with self._lock:
            self._send_call(name, args)

    def call(self, name, *args):
        logger.debug("%s%r method call", name, args)
        if len(self._results) >= RESULT_BUF_SIZE:
            logger.error("Cannot call Guitarix %s%r - too many methods pending", name, args)
            raise GuitarixClientError("Too many methods pending")
        deadline = time.time() + TIMEOUT
        with self._lock:
            self._req_id += 1
            req_id = str(self._req_id)
            result_cond = threading.Condition(self._lock)
            result = result_cond
            self._results[req_id] = result
            try:
                self._send_call(name, args, req_id)
                while result is result_cond:
                    with self._lock:
                        result = self._results[req_id]
                        if result is not result_cond:
                            break
                        now = time.time()
                        if not result_cond.wait(max(0.1, deadline - now)):
                            raise GuitarixClientError("Method call timeout")
            finally:
                try:
                    del self._results[req_id]
                except KeyError:
                    pass
        if isinstance(result, Exception):
            raise result
        return result

    def _run(self):
        try:
            data = b""
            while self._socket:
                try:
                    frame = self._socket.recv(4096)
                except socket.timeout:
                    continue
                except socket.error as err:
                    logger.warning("Cannot read from Guitarix: %s", err)
                    break
                if not frame:
                    logger.debug("EOF on guitarix connection")
                    break
                data += frame
                if b"\n" not in data:
                    continue
                lines = data.split(b"\n")
                for msg_s in lines[:-1]:
                    logger.debug("Received: %r", msg_s)
                    try:
                        msg = json.loads(msg_s.decode("utf-8"))
                    except ValueError as err:
                        logger.warning("Guitarix message parse error: %r: %r",
                                       msg_s, err)
                    self._handle_incoming_msg(msg)
                data = lines[-1]
            self.disconnect()
        finally:
            self._thread = None

    def _handle_incoming_msg(self, msg):
        if "method" in msg:
            logger.debug("Got method/notification: %r", msg)
            self._call_observers(msg["method"], *msg.get("params", []))
            return
        elif "result" in msg:
            return self._handle_result(msg)
        elif "error" in msg:
            return self._handle_error(msg)
        else:
            logger.info("Got unexpected message: %r", msg)
            return

    def _handle_result(self, msg):
        try:
            req_id = msg["id"]
            result = msg["result"]
        except KeyError as key:
            logger.warning("Missing property in message: %r: %r", msg, key)
            return
        with self._lock:
            try:
                cond = self._results[req_id]
            except KeyError:
                logger.warning("Unexpected result: %r", msg)
                return
            if not isinstance(cond, threading.Condition):
                logger.warning("Unexpected result (duplicate?): %r", msg)
                return
            self._results[req_id] = result
            cond.notify_all()

    def _handle_error(self, msg):
        try:
            req_id = msg["id"]
            error = msg["error"]
        except KeyError as key:
            logger.warning("Missing property in message: %r: %r", msg, key)
            return
        with self._lock:
            try:
                cond = self._results[req_id]
            except KeyError:
                logger.warning("Unexpected error: %r", msg)
                return
            if not isinstance(cond, threading.Condition):
                logger.warning("Unexpected error (duplicate?): %r", msg)
                return
            self._results[req_id] = GuitarixRPCError(result)
            cond.notify_all()

