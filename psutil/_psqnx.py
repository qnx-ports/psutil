# Copyright (c) 2026, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""QNX platform implementation."""

import errno
import enum
import functools
import os

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


# TODO
def virtual_memory():
    """System virtual memory as a namedtuple."""
    total, active, inactive, wired, free, speculative = cext.virtual_mem()
    # This is how Zabbix calculate avail and used mem:
    # https://github.com/zabbix/zabbix/blob/master/src/libs/zbxsysinfo/osx/memory.c
    # Also see: https://github.com/giampaolo/psutil/issues/1277
    avail = inactive + free
    used = active + wired
    # This is NOT how Zabbix calculates free mem but it matches "free"
    # cmdline utility.
    free -= speculative
    percent = usage_percent((total - avail), total, round_=1)
    return ntp.svmem(
        total, avail, percent, used, free, active, inactive, wired
    )


def swap_memory():
    """Swap system memory as a (total, used, free, sin, sout) tuple."""
    total, used, free, sin, sout = cext.swap_mem()
    percent = usage_percent(used, total, round_=1)
    return ntp.sswap(total, used, free, percent, sin, sout)


# malloc / heap functions
# heap_info = cext.heap_info
# heap_trim = cext.heap_trim


# =====================================================================
# --- CPU
# =====================================================================


def cpu_times():
    """Return system CPU times as a namedtuple."""
    user, nice, system, idle = cext.cpu_times()
    return ntp.scputimes(user, nice, system, idle)


def per_cpu_times():
    """Return system CPU times as a named tuple."""
    ret = []
    for cpu_t in cext.per_cpu_times():
        user, nice, system, idle = cpu_t
        item = ntp.scputimes(user, nice, system, idle)
        ret.append(item)
    return ret


def cpu_count_logical():
    """Return the number of logical CPUs in the system."""
    return cext.cpu_count_logical()


def cpu_count_cores():
    """Return the number of CPU cores in the system."""
    # Not supported
    # QNX isn't aware of hyperthreaded cores
    return None


def cpu_stats():
    ctx_switches, interrupts, soft_interrupts, syscalls, _traps = (
        cext.cpu_stats()
    )
    return ntp.scpustats(ctx_switches, interrupts, soft_interrupts, syscalls)


def cpu_freq():
    return [ntp.scpufreq(x, y, z) for x,y,z in cext.cpu_freq()]

# =====================================================================
# --- disks
# =====================================================================


# disk_usage = _psposix.disk_usage
# disk_io_counters = cext.disk_io_counters


def disk_partitions(all=False):
    """Return mounted disk partitions as a list of namedtuples."""
    retlist = []
    partitions = cext.disk_partitions()
    for partition in partitions:
        device, mountpoint, fstype, opts = partition
        if device == 'none':
            device = ''
        if not all:
            if not os.path.isabs(device) or not os.path.exists(device):
                continue
        ntuple = ntp.sdiskpart(device, mountpoint, fstype, opts)
        retlist.append(ntuple)
    return retlist


# =====================================================================
# --- sensors
# =====================================================================


def sensors_battery():
    """Return battery information."""
    try:
        percent, minsleft, power_plugged = cext.sensors_battery()
    except NotImplementedError:
        # no power source - return None according to interface
        return None
    power_plugged = power_plugged == 1
    if power_plugged:
        secsleft = _common.POWER_TIME_UNLIMITED
    elif minsleft == -1:
        secsleft = _common.POWER_TIME_UNKNOWN
    else:
        secsleft = minsleft * 60
    return ntp.sbattery(percent, secsleft, power_plugged)


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
    # Note: on macOS this will fail with AccessDenied unless
    # the process is owned by root.
    ret = []
    for pid in pids():
        try:
            cons = Process(pid).net_connections(kind)
        except NoSuchProcess:
            continue
        else:
            if cons:
                for c in cons:
                    c = list(c) + [pid]
                    ret.append(ntp.sconn(*c))
    return ret


# =====================================================================
# --- other system functions
# =====================================================================


def boot_time():
    return cext.boot_time()



def adjust_proc_create_time(ctime):
    """Account for system clock updates."""
    if INIT_BOOT_TIME == 0:
        return ctime

    diff = INIT_BOOT_TIME - boot_time()
    if diff == 0 or abs(diff) < 1:
        return ctime

    debug("system clock was updated; adjusting process create_time()")
    if diff < 0:
        return ctime - diff
    return ctime + diff


def users():
    """Return currently connected users as a list of namedtuples."""
    retlist = []
    rawlist = cext.users()
    for item in rawlist:
        user, tty, hostname, tstamp, pid = item
        if tty == '~':
            continue  # reboot or shutdown
        if not tstamp:
            continue
        nt = ntp.suser(user, tty or None, hostname or None, tstamp, pid)
        retlist.append(nt)
    return retlist


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
        ctime = self.self.proc_basic_info()[procbasicinfo_map['start_time']]
        if not monotonic:
            ctime = adjust_proc_create_time(ctime)
        return ctime

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
        families, types = conn_tmap[kind]
        rawlist = cext.proc_net_connections(self.pid, families, types)
        ret = []
        for item in rawlist:
            fd, fam, type, laddr, raddr, status = item
            nt = conn_to_ntuple(
                fd, fam, type, laddr, raddr, status, TCP_STATUSES
            )
            ret.append(nt)
        return ret

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
