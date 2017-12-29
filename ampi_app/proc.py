"""Process management."""

import sys
import os
import logging
import time
import errno
import subprocess
import fcntl
import threading

from gi.repository import GObject

logger = logging.getLogger("proc")

class Processes:
    def __init__(self):
        pass
    def list(self):
        for dirname in os.listdir("/proc"):
            path = os.path.join("/proc", dirname)
            if not os.path.isdir(path):
                continue
            try:
                pid = int(dirname)
            except ValueError:
                continue
            cmdline_p = os.path.join(path, "cmdline")
            try:
                with open(cmdline_p, "rb") as cmdline_f:
                    cmdline = cmdline_f.read()
            except OSError as err:
                if err.errno not in (errno.EPERM, errno.EACCES):
                    logger.debug("%s: %s", cmdline_p, err)
                continue
            name = cmdline.split(b"\000", 1)[0].decode("utf-8", "replace")
            exe_p = os.path.join(path, "exe")
            try:
                exe_name = os.readlink(exe_p)
            except OSError as err:
                if err.errno not in (errno.EPERM, errno.EACCES):
                    logger.debug("%s: %s", exe_p, err)
                exe_name = None
            yield pid, name, exe_name
    def find(self, query):
        for pid, name, exe_name in self.list():
            if "/" in query:
                if name == query or exe_name == query:
                    yield pid, name, exe_name
            else:
                if (name and os.path.basename(name) == query
                        or exe_name and os.path.basename(exe_name) == query):
                    yield pid, name, exe_name
    def killall(self, name):
        pids = set(proc[0] for proc in self.find(name))
        if not pids:
            logger.debug("killall(%r): nothing to kill", name)
            return
        logger.info("killing %r (%s)", name, ",".join(str(pid) for pid in pids))
        for pid in sorted(pids):
            try:
                os.kill(pid, 15)
            except OSError as err:
                if err.errno != errno.ESRCH:
                    logger.warning("cannot kill %r (%i): %s", name, pid, err)
                pids.remove(pid)

        # wait up to 5 seconds for them to die
        for i in range(25):
            if not pids:
                # all dead
                return
            time.sleep(0.2)
            for pid in sorted(pids):
                try:
                    os.kill(pid, 0)
                except OSError as err:
                    if err.errno != errno.ESRCH:
                        logger.warning("cannot kill -0 %r (%i): %s", name, pid, err)
                    pids.remove(pid)

        # kill with fire!
        for pid in sorted(pids):
            try:
                os.kill(pid, 9)
            except OSError as err:
                if err.errno != errno.ESRCH:
                    logger.warning("cannot kill -9 %r (%i): %s", name, pid, err)


def unblock_fd(stream):
    fd = stream.fileno()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

class Nanny:
    """Child process monitor."""
    def __init__(self, name, command, kill_list=None, restart=True, callback=None):
        self.name = name
        self.command = command
        self.kill_list = kill_list
        self.logger = logging.getLogger("proc." + name)
        self.callback = callback
        self._procs = Processes()
        self._child = None
        self._thread = None
        self._should_be_running = False
        if kill_list:
            for name in kill_list:
                self._procs.killall(name)
    def __del__(self):
        self.stop()

    def start(self):
        if self._thread or self._child:
            return
        if self.kill_list:
            for name in self.kill_list:
                self._procs.killall(name)

        logger.info("Starting: %s", " ".join(self.command))
        self._child = subprocess.Popen(self.command,
                                       stdin=open("/dev/null", "rb"),
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT)
        self._thread = threading.Thread(target=self.process_output,
                                        args=(self._child,),
                                        name="{} nanny".format(self.name),
                                        daemon=True)
        self._should_be_running = True
        self._thread.start()
        if self.callback:
            self.callback(True)

    def let_it_stop(self):
        self._should_be_running = False

    def stop(self):
        self._should_be_running = False
        child = self._child
        if child:
            logger.info("Terminating %s with SIGTERM...", self.name)
            child.terminate()
            try:
                rc = child.wait(2)
            except subprocess.TimeoutExpired:
                logger.info("Killing %s with SIGKILL...", self.name)
                child.kill()
                time.sleep(0.2)
            self._child = None

        if self.kill_list:
            for name in self.kill_list:
                self._procs.killall(name)

        thread = self._thread
        if thread:
            thread.join(5)
            if thread.is_alive():
                logger.warning("{} nanny thread won't die".format(self.name))
            self._thread = None

    def process_output(self, child):
        """Proccess output of the child process."""
        for line in child.stdout:
            line = line.rstrip(b"\r\n").decode("utf-8", "replace")
            self.logger.info("[%s] %s", self.name, line)
        rc = child.wait()
        self._thread = None
        self._child = None
        if rc > 0 or self._should_be_running:
            self.logger.warning("%s exitted with status %i", self.name, rc)
        else:
            self.logger.debug("%s exitted with status %i", self.name, rc)
        if self.callback:
            self.callback(False)
        if self._should_be_running:
            GObject.timeout_add(1000, self.restart_if_needed)

    def restart_if_needed(self):
        if self._should_be_running:
            if not self._child:
                logger.debug("restart_if_needed: %s needed and not running",
                             self.name)
                self.start()
            else:
                logger.debug("restart_if_needed: %s needed and running",
                             self.name)
        else:
            logger.debug("restart_if_needed: %s not needed", self.name)

    def restart(self):
        if self.is_started():
            self.stop()
        self.start()

    def is_started(self):
        return bool(self._thread) or bool(self._child)

if __name__ == "__main__":
    print("Processes:")
    proc = Processes()
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            for pid, name, exe_name in proc.find(arg):
                print("{:7d} {} {}".format(pid, exe_name, name))
    else:
        for pid, name, exe_name in proc.list():
            print("{:7d} {} {}".format(pid, exe_name, name))
