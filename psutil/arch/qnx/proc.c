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

PyObject *
psutil_proc_basic_info(PyObject *self, PyObject *args) {
    procfs_info info;
    int fd;
    char fn[PATH_MAX];
    int pid;

    if (!PyArg_ParseTuple(args, "i", &pid))
        return NULL;

    snprintf(fn, sizeof fn, "/proc/%d/as", pid);

    fd = open(fn, O_RDONLY);
    if (fd == NOFD) {
        return NULL;
    }

    errno = devctl(fd, DCMD_PROC_INFO, &info, sizeof info, 0);
    close(fd);
    if (errno != EOK) {
        return NULL;
    }

    return Py_BuildValue(
        "iKKKBiiiiiii",
        info.parent,
        info.start_time,
        info.utime,
        info.stime,
        info.priority,
        info.num_threads,
        info.uid,
        info.gid,
        info.euid,
        info.egid,
        info.suid,
        info.sgid
    );
}
