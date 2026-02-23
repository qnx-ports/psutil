/*
 * Copyright (c) 20026, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include <Python.h>
#include <sys/types.h>

PyObject *psutil_net_io_counters(PyObject *self, PyObject *args);
PyObject *psutil_boot_time(PyObject *self, PyObject *args);
PyObject *psutil_cpu_count_logical(PyObject *self, PyObject *args);
PyObject *psutil_cpu_count_cores(PyObject *self, PyObject *args);
