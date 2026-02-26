/*
 * Copyright (c) 2026, Jay Loden, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include <Python.h>
#include <sys/procfs.h>
#include <string.h>
#include <stdlib.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sched.h>
#include <errno.h>

#include "../../arch/all/init.h"

PyObject *
psutil_proc_basic_info(PyObject *self, PyObject *args) {
    debug_process_t p_info;
    debug_thread_t  t_info;
    int fd;
    char fn[PATH_MAX];
    int pid;

    if (!PyArg_ParseTuple(args, "i", &pid))
        return NULL;

    snprintf(fn, sizeof fn, "/proc/%d/as", pid);

    fd = open(fn, O_RDONLY);
    if (fd == NOFD) {
        psutil_oserror_ad("open");
        return NULL;
    }

    errno = devctl(fd, DCMD_PROC_INFO, &p_info, sizeof p_info, 0);
    if (errno != EOK) {
        psutil_oserror_ad("devctl -> DMCD_PROC_INFO");
        return NULL;
    }

    t_info.tid = 1;
    errno = devctl(fd, DCMD_PROC_TIDSTATUS, &t_info, sizeof t_info, 0);
    if (errno != EOK) {
        psutil_oserror_ad("devctl -> DMCD_PROC_STATUS");
        return NULL;
    }

    close(fd);

    return Py_BuildValue(
        "iKKKBiiiiiiB",
        p_info.parent,
        p_info.start_time,
        p_info.utime,
        p_info.stime,
        p_info.num_threads,
        p_info.uid,
        p_info.gid,
        p_info.euid,
        p_info.egid,
        p_info.suid,
        p_info.sgid,
        t_info.state
    );
}

// Get PID priority.
PyObject *
psutil_proc_priority_get(PyObject *self, PyObject *args) {
    pid_t pid;
    struct sched_param prio;

    if (!PyArg_ParseTuple(args, _Py_PARSE_PID, &pid))
        return NULL;

    if (sched_getparam(pid, &prio))
        return psutil_oserror();
    return Py_BuildValue("i", prio.sched_curpriority);
}


// Set PID priority.
PyObject *
psutil_proc_priority_set(PyObject *self, PyObject *args) {
    pid_t pid;
    int priority;
    struct sched_param prio;

    if (!PyArg_ParseTuple(args, _Py_PARSE_PID "i", &pid, &priority))
        return NULL;

    prio.sched_priority = SCHED_PRIO_LIMIT_SATURATE(priority);

    if(sched_setparam(pid, &prio))
        return psutil_oserror();

    Py_RETURN_NONE;
}
