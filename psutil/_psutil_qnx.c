/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 */

// QNX-specific functions.

#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif

#include <Python.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <netinet/tcp_fsm.h>  // for TCP connection states

#include "arch/all/init.h"

static PyMethodDef mod_methods[] = {
    {"check_pid_range", psutil_check_pid_range, METH_VARARGS},
    {"set_debug", psutil_set_debug, METH_VARARGS},
    {"boot_time", psutil_boot_time, METH_VARARGS},
    {"cpu_count_logical", psutil_cpu_count_logical, METH_VARARGS},
    {"cpu_freq", psutil_cpu_freq, METH_VARARGS},
    {"proc_basic_info", psutil_proc_basic_info, METH_VARARGS},

    {"net_io_counters", psutil_net_io_counters, METH_VARARGS},
    {NULL, NULL, 0, NULL}
};


static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_psutil_qnx",
    NULL,
    -1,
    mod_methods,
    NULL,
    NULL,
    NULL,
    NULL
};


PyObject *
PyInit__psutil_qnx(void) {
    PyObject *mod = PyModule_Create(&moduledef);
    if (mod == NULL)
        return NULL;

#ifdef Py_GIL_DISABLED
    if (PyUnstable_Module_SetGIL(mod, Py_MOD_GIL_NOT_USED))
        return NULL;
#endif

    if (psutil_setup() != 0)
        return NULL;
    if (psutil_posix_add_constants(mod) != 0)
        return NULL;
    if (psutil_posix_add_methods(mod) != 0)
        return NULL;

    if (PyModule_AddIntConstant(mod, "version", PSUTIL_VERSION))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_CLOSED", TCPS_CLOSED))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_CLOSING", TCPS_CLOSING))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_CLOSE_WAIT", TCPS_CLOSE_WAIT))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_LISTEN", TCPS_LISTEN))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_ESTABLISHED", TCPS_ESTABLISHED))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_SYN_SENT", TCPS_SYN_SENT))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_SYN_RECEIVED", TCPS_SYN_RECEIVED))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_FIN_WAIT_1", TCPS_FIN_WAIT_1))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_FIN_WAIT_2", TCPS_FIN_WAIT_2))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_LAST_ACK", TCPS_LAST_ACK))
        return NULL;
    if (PyModule_AddIntConstant(mod, "TCPS_TIME_WAIT", TCPS_TIME_WAIT))
        return NULL;
    if (PyModule_AddIntConstant(mod, "PSUTIL_CONN_NONE", PSUTIL_CONN_NONE))
        return NULL;

    return mod;
}
