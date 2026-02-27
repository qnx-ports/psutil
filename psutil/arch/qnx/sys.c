/*
 * Copyright (c) 2026, Jay Loden, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include <Python.h>
#include <sys/syspage.h>

#include "../../arch/all/init.h"

// Return a Python float indicating the system boot time expressed in
// seconds since the epoch.
PyObject *
psutil_boot_time(PyObject *self, PyObject *args) {
    time_t boot_time;

    boot_time = _SYSPAGE_ENTRY(_syspage_ptr, qtime)->boot_time;

    return Py_BuildValue("d", (double)boot_time);
}
