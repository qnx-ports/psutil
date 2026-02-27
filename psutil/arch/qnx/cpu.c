/*
 * Copyright (c) 2026, Jay Loden, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

#include <Python.h>
#include <sys/syspage.h>
#include <stdio.h>

#include "init.h"

PyObject *
psutil_cpu_count_logical(PyObject *self, PyObject *args) {
    return Py_BuildValue("i", _syspage_ptr->num_cpu);
}

PyObject *
psutil_cpu_freq(PyObject *self, PyObject *args) {
    PyObject *py_tuple = NULL;
    PyObject *py_retlist = PyList_New(0);

    struct cpuinfo_entry *cpuinfo = (struct cpuinfo_entry *)_SYSPAGE_ENTRY(
        _syspage_ptr, cpuinfo
    );
    ;
    size_t cpuinfo_sz = _SYSPAGE_ELEMENT_SIZE(_syspage_ptr, cpuinfo);

    struct cpuinfo_entry *cpu = cpuinfo;
    int i = 0;
    while (i < _syspage_ptr->num_cpu) {
        py_tuple = Py_BuildValue(
            "(Idd)", cpu->speed, (double)0.0, (double)0.0
        );
        if (!py_tuple) {
            goto error;
        }

        if (PyList_Append(py_retlist, py_tuple)) {
            goto error;
        }
        Py_CLEAR(py_tuple);

        i++;
        cpu = SYSPAGE_ARRAY_ADJ_OFFSET(cpuinfo, cpu, cpuinfo_sz);
    }

    return py_retlist;

error:
    Py_XDECREF(py_tuple);
    Py_DECREF(py_retlist);
    return NULL;
}
