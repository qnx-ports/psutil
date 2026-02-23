/*
 * Copyright (c) 2026, Jay Loden, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include <Python.h>
#include "../../arch/all/init.h"
#include <sys/syspage.h>
#include <stdio.h>

PyObject *
psutil_cpu_count_logical(PyObject *self, PyObject *args) {
    return Py_BuildValue("i", _syspage_ptr->num_cpu);
}
