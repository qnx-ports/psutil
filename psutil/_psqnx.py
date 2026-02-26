# Copyright (c) 2026, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""QNX platform implementation."""

import errno
import enum
import functools
import os
import re

from . import _common
from . import _ntuples as ntp
from . import _psposix
from . import _psutil_qnx as cext
from ._common import ENCODING
from ._common import get_procfs_path
from ._common import AccessDenied
from ._common import NoSuchProcess
from ._common import ZombieProcess
from ._common import conn_tmap
from ._common import conn_to_ntuple
from ._common import debug
from ._common import isfile_strict
from ._common import memoize_when_activated
from ._common import parse_environ_block
from ._common import usage_percent

__extra__all__ = [
    "PROCFS_PATH",
]

# =====================================================================
# --- globals
# =====================================================================

PAGESIZE = cext.getpagesize()
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
AF_LINK = cext.AF_LINK

TCP_STATUSES = {
    cext.TCPS_ESTABLISHED: _common.CONN_ESTABLISHED,
    cext.TCPS_SYN_SENT: _common.CONN_SYN_SENT,
    cext.TCPS_SYN_RECEIVED: _common.CONN_SYN_RECV,
    cext.TCPS_FIN_WAIT_1: _common.CONN_FIN_WAIT1,
    cext.TCPS_FIN_WAIT_2: _common.CONN_FIN_WAIT2,
    cext.TCPS_TIME_WAIT: _common.CONN_TIME_WAIT,
    cext.TCPS_CLOSED: _common.CONN_CLOSE,
    cext.TCPS_CLOSE_WAIT: _common.CONN_CLOSE_WAIT,
    cext.TCPS_LAST_ACK: _common.CONN_LAST_ACK,
    cext.TCPS_LISTEN: _common.CONN_LISTEN,
    cext.TCPS_CLOSING: _common.CONN_CLOSING,
    cext.PSUTIL_CONN_NONE: _common.CONN_NONE,
}

PROC_STATUSES = {
    0:  "dead",
    1:  "running",
    2:  "ready",
    3:  "stopped",
    4:  "send",
    5:  "receive",
    6:  "reply",
    7:  "mq_send",
    8:  "mq_receive",
    9:  "waitpage",
    10: "sigsuspend",
    11: "sigwaitinfo",
    12: "nanosleep",
    13: "mutex",
    14: "condvar",
    15: "join",
    16: "intr",
    17: "sem",
    18: "waitctx",
    19: "rwlock_read",
    20: "rwlock_write",
    21: "barrier",
    22: "pipe"
}

pidtaskinfo_map = dict(
    cpuutime=0,
    cpustime=1,
    rss=2,
    vms=3,
    pfaults=4,
    pageins=5,
    numthreads=6,
    volctxsw=7,
)

procbasicinfo_map = dict (
    parent_pid=0,
    start_time=1,
    utime=2,
    stime=3,
    num_threads=4,
    uid=5,
    gid=6,
    euid=7,
    egid=8,
    suid=9,
    sgid=10,
    status=11
)


# =====================================================================
# --- memory
# =====================================================================


def virtual_memory():
    """System virtual memory as a namedtuple."""
    stats = {}
    with open(f"{get_procfs_path()}/vm/stats", 'r') as f:
        for _line in f:
            line = _line.strip()
            if len(line) == 0:
                continue
            s1 = line.split("=")
            if len(s1) < 2:
                continue
            key=s1[0]
            s2 = s1[1].split(" ")
            try:
                if s2[0].startswith("0x"):
                    val = int(s2[0], 16) * PAGESIZE
                else:
                    val = int(s2[0])
            except Exception as e:
                print(e)
                continue
            stats[key] = val

    total = stats.get("page_count", 0)
    available = stats.get("vmem_avail", 0)

    if total > 0:
        percent = (total - available) / total * 100
    else:
        percent = 0
    free = stats.get("pages_free", 0)

    # Parse the stats
    return ntp.svmem(total, available, percent, free)

def swap_memory():
    """Swap system memory as a (total, used, free, sin, sout) tuple."""
    # There is no swap on QNX
    return ntp.sswap(0, 0, 0, 0, 0)


# =====================================================================
# --- CPU
# =====================================================================


def cpu_times():
    """Return system CPU times as a namedtuple."""
    # Not supported
    return None

def per_cpu_times():
    """Return system CPU times as a named tuple."""
    # Not supported
    return None


def cpu_count_logical():
    """Return the number of logical CPUs in the system."""
    return cext.cpu_count_logical()


def cpu_count_cores():
    """Return the number of CPU cores in the system."""
    # Not supported
    # QNX isn't aware of hyperthreaded cores
    return None

def cpu_stats():
    # Not supported
    return None


def cpu_freq():
    return [ntp.scpufreq(x, y, z) for x,y,z in cext.cpu_freq()]

# =====================================================================
# --- disks
# =====================================================================


# disk_usage = _psposix.disk_usage
# disk_io_counters = cext.disk_io_counters

def disk_partitions(all=False):
    """Return mounted disk partitions as a list of namedtuples."""
    # Not supported
    return None


# =====================================================================
# --- sensors
# =====================================================================

def sensors_battery():
    """Return battery information."""
    # Not supported
    return None


# =====================================================================
# --- network
# =====================================================================


net_io_counters = cext.net_io_counters
net_if_addrs = cext.net_if_addrs

def net_if_stats():
    """Get NIC stats (isup, duplex, speed, mtu)."""
    names = net_io_counters().keys()
    ret = {}
    for name in names:
        try:
            mtu = cext.net_if_mtu(name)
            flags = cext.net_if_flags(name)
            duplex, speed = cext.net_if_duplex_speed(name)
        except OSError as err:
            # https://github.com/giampaolo/psutil/issues/1279
            if err.errno != errno.ENODEV:
                raise
        else:
            if hasattr(_common, 'NicDuplex'):
                duplex = _common.NicDuplex(duplex)
            output_flags = ','.join(flags)
            isup = 'running' in flags
            ret[name] = ntp.snicstats(isup, duplex, speed, mtu, output_flags)
    return ret

def net_connections(kind='inet'):
    """System-wide network connections."""
    # Not supported
    # Technically possible to do, but requires headers unavailable in this current version
    return []


# =====================================================================
# --- other system functions
# =====================================================================


def boot_time():
    return cext.boot_time()



def users():
    """Return currently connected users as a list of namedtuples."""
    # Not supported
    return []


# =====================================================================
# --- processes
# =====================================================================


def pids():
    """Returns a list of PIDs currently running on the system."""
    path = get_procfs_path().encode(ENCODING)
    return [int(x) for x in os.listdir(path) if x.isdigit()]


pid_exists = _psposix.pid_exists


def wrap_exceptions(fun):
    """Decorator which translates bare OSError exceptions into
    NoSuchProcess and AccessDenied.
    """

    @functools.wraps(fun)
    def wrapper(self, *args, **kwargs):
        pid, ppid, name = self.pid, self._ppid, self._name
        try:
            return fun(self, *args, **kwargs)
        except ProcessLookupError as err:
            if cext.proc_is_zombie(pid):
                raise ZombieProcess(pid, name, ppid) from err
            raise NoSuchProcess(pid, name) from err
        except PermissionError as err:
            raise AccessDenied(pid, name) from err
        except cext.ZombieProcessError as err:
            raise ZombieProcess(pid, name, ppid) from err

    return wrapper


class Process:
    """Wrapper class around underlying C implementation."""

    __slots__ = ["_cache", "_name", "_ppid", "_procfs_path", "pid"]

    def __init__(self, pid):
        self.pid = pid
        self._name = None
        self._ppid = None
        self._procfs_path = get_procfs_path()

    @wrap_exceptions
    @memoize_when_activated
    def _proc_basic_info(self):
        return cext.proc_basic_info(self.pid)

    @wrap_exceptions
    @memoize_when_activated
    def _proc_vmstats(self):
        stats = {}
        f = self._readfile(f"{self._procfs_path}/{self.pid}/vmstat")
        for line in f.split("\n"):
            if len(line) == 0:
                continue
            s1 = line.split("=")
            if len(s1) < 2:
                continue
            s2 = s1[0].split(".")
            if len(s1) < 2:
                continue
            key = s2[1]
            s3 = s1[1].split(" ")
            try:
                if s3[0].startswith("0x"):
                    val = int(s3[0], 16) * PAGESIZE
                else:
                    val = int(s3[0])
            except:
                continue
            stats[key] = val
        return stats

    def _readfile(self, path):
        try:
            with open(path, 'r') as f:
                return f.read().strip('\x00')
        except:
            return ""

    def oneshot_enter(self):
        self._proc_basic_info.cache_activate(self)
        self._proc_vmstats.cache_activate(self)

    def oneshot_exit(self):
        self._proc_basic_info.cache_deactivate(self)
        self._proc_vmstats.cache_deactivate(self)

    @wrap_exceptions
    def name(self):
        # POSSIBLE WITH DCMD_PROC_MAPDEBUG_BASE
        return "UNIMPLEMENTED"

    @wrap_exceptions
    def exe(self):
        return self._readfile(f"{self._procfs_path}/{self.pid}/exefile")

    @wrap_exceptions
    def cmdline(self):
        return self._readfile(f"{self._procfs_path}/{self.pid}/cmdline")

    @wrap_exceptions
    def environ(self):
        # Not supported
        # Theres no way QNX let's us read someone elses ENV variables without root
        return {}

    @wrap_exceptions
    def ppid(self):
        self._ppid = self._proc_basic_info()[procbasicinfo_map['parent']]
        return self._ppid

    @wrap_exceptions
    def cwd(self):
        # Not supported
        # We don't have this info
        return ""

    @wrap_exceptions
    def uids(self):
        rawtuple = self._proc_basic_info()
        return ntp.puids(
            rawtuple[procbasicinfo_map['uid']],
            rawtuple[procbasicinfo_map['euid']],
            rawtuple[procbasicinfo_map['suid']],
        )

    @wrap_exceptions
    def gids(self):
        rawtuple = self._proc_basic_info()
        return ntp.puids(
            rawtuple[kinfo_proc_map['gid']],
            rawtuple[kinfo_proc_map['egid']],
            rawtuple[kinfo_proc_map['sgid']],
        )

    @wrap_exceptions
    def terminal(self):
        # Not supported
        return None

    @wrap_exceptions
    def memory_info(self):
        rawdict = self._proc_vmstats()
        return ntp.pmem(rawdict["rss"], rawdict["map_size"])

    @wrap_exceptions
    def memory_full_info(self):
        rawdict = self._proc_vmstats()
        return ntp.pfullmem(
                rawdict["rss"],
                rawdict["map_size"],
                rawdict["map_phys"],
                rawdict["map_shared"],
                rawdict["map_private"],
                rawdict["vm_region"],
                rawdict["vm_map"],
                rawdict["anon_rsv"],
                rawdict["rlimit_data"]
            )

    @wrap_exceptions
    def cpu_times(self):
        rawtuple = self.proc_basic_info()
        return ntp.pcputimes(
            rawtuple[pidtaskinfo_map['utime'] / CLOCK_TICKS],
            rawtuple[pidtaskinfo_map['stime'] / CLOCK_TICKS],
            # children user / system times are not retrievable (set to 0)
            0.0,
            0.0,
        )

    @wrap_exceptions
    def create_time(self, monotonic=False):
        return self.self.proc_basic_info()[procbasicinfo_map['start_time']]

    @wrap_exceptions
    def num_ctx_switches(self):
        # Doubt we have this information
        return ntp.pctxsw(0, 0)

    @wrap_exceptions
    def num_threads(self):
        ctime = self.self.proc_basic_info()[procbasicinfo_map['num_threads']]

    @wrap_exceptions
    def open_files(self):
        # Not supported
        return []

    @wrap_exceptions
    def net_connections(self, kind='inet'):
        # Not supported
        # Technically possible to do, but requires headers unavailable in this current version
        return []

    @wrap_exceptions
    def num_fds(self):
        return 0

    @wrap_exceptions
    def wait(self, timeout=None):
        return _psposix.wait_pid(self.pid, timeout)

    @wrap_exceptions
    def nice_get(self):
        return cext.proc_priority_get(self.pid)

    @wrap_exceptions
    def nice_set(self, value):
        return cext.proc_priority_set(self.pid, value)

    @wrap_exceptions
    def status(self):
        code = self._proc_basic_info()[procbasicinfo_map["status"]]
        # XXX is '?' legit? (we're not supposed to return it anyway)
        return PROC_STATUSES.get(code, '?')

    @wrap_exceptions
    def threads(self):
        return [ntp.pthread(x,y) for x,y in cext.proc_threads(self.pid)]
