#!/usr/bin/env python3

import os
import pty
import tty
from tty import setraw, tcgetattr, tcsetattr
from select import select
import atexit
import termios
import struct
import fcntl
import codecs
import re
import sys
import shlex
import random
import time
import queue
from threading import Thread

blamaster = open('/tmp/blamaster', 'ab')
blastdin  = open('/tmp/blastdin',  'ab')

log = open('/tmp/thrcliplog', 'a')
oprint = print
def print(*args):
    oprint(*args, file = log)
    log.flush()

start_marker = b"_.oOO"

end_marker = b"OOo._"

hold = bytearray(b'')

piggy = bytearray(b'')

marker = start_marker
j = 0


qquit = False

def alternate_marker(marker):
    if marker == start_marker:
        return end_marker
    else:
        return start_marker

Qnaus = queue.Queue()

def piggy_end():
    global piggy
    Qnaus.put(piggy)
    piggy = bytearray(b'')
    print('-- piggy payload read', piggy.decode())

def do_oink(arr):
    global j
    global marker
    global hold
    global piggy
    print(where, 'do_ink', arr, 'holding', hold)
    ret = bytearray(b'')

    for i, x in enumerate(arr):
        if x == marker[j]:
#             print(chr(x), i, j, marker[j], 'read marker')
            j+=1
            hold.append( x )

            if j == len(marker):               # marker entirely read
                if marker == end_marker:       # we are in piggy mode
                    piggy_end()

                marker = alternate_marker(marker)
                print('  entire marker read. now waiting for', marker)
                j = 0
                hold = bytearray(b'')

        else:
#             print(chr(x), i, j, marker[j], '  no marker or cancel marker')
            if marker == end_marker:           # piggy mode
                if j > 0:                      # marker partly read and cancelling marker
                    piggy = piggy + hold       # release the hold
                piggy.append( x )
            else: # if marker == start_marker    transparent mode
                if j > 0:                      # marker partly read and cancelling marker
                    ret = ret + hold           # release the hold
                ret.append( x )

            j = 0 # cancel marker start 
            hold = bytearray(b'')

    return ret

def ensure_fifo(fn):
    try:
        os.mkfifo(fn)
    except OSError as e:
        print(fn, "gibt's scho")

def quote(fn):
    """quoting bytes-strings"""
    return shlex.quote(fn.decode('utf8')).encode('utf8')


termsize = ()
def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def master_read(fd):
    global termsize

    ts = os.get_terminal_size()
    if (ts != termsize):
        termsize = ts
        set_winsize(fd, termsize[1], termsize[0])

    data = os.read(fd, 1024)
#     blamaster.write(data) 
#     blamaster.flush()

    print(where,'master_read', data)
    if local:
        ret = do_oink(data)
        swallowed = len(data) > 0 and len(ret) == 0
        return ret, swallowed
    else:
        return data, False


def write_naus():
    global qquit
    global Qnaus
    print('enter naus: get Qnaus')
    while not qquit:
        print('naus: get Qnaus')
        x = Qnaus.get()
        fd = open(naus_fn, 'w')
        fd.write(x.decode())
        fd.close()
        print('naus:', x)

    print('naus: -> quit')
#     os.remove(naus_fn)


STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2

CHILD = 0

nei_fd = None

def spawn(argv, master_read, stdin_read):
    """Create a spawned process."""
    if isinstance(argv, str):
        argv = (argv,)
#     sys.audit('pty.spawn', argv)

    pid, master_fd = pty.fork()
    if pid == CHILD:
        os.execlp(argv[0], *argv)

    try:
        mode = tcgetattr(STDIN_FILENO)
        setraw(STDIN_FILENO)
        restore = True
    except tty.error:    # This is the same as termios.error
        restore = False

    global nei_fd
    nei_fd = os.open(nei_fn, os.O_RDONLY or os.O_NONBLOCK)

    try:
        _copy(master_fd, master_read, stdin_read, _read)
    finally:
        if restore:
            tcsetattr(STDIN_FILENO, tty.TCSAFLUSH, mode)

    os.close(master_fd)
    return os.waitpid(pid, 0)[1]

def _read(fd):
    """Default read function."""
    return os.read(fd, 1024)

## Remoteward we piggyback on stdin
## that means for stdin_read: 
## when we run remotely, we look out on stdin for markers
## and when we run locally, we are transparent
def stdin_read(fd):
    data = os.read(fd, 1024)
#     blastdin.write(data) 
#     blastdin.flush()

    print(where, 'stdin_read', data)
    if local:
        return data, False
    else:
        ret = do_oink(data)
        swallowed = len(data) > 0 and len(ret) == 0
        return ret, swallowed

def _copy(master_fd, master_read, stdin_read, nei_read):
    """Parent copy loop.
    Copies
            pty master -> standard output   (master_read)
            standard input -> pty master    (stdin_read)"""

    global nei_fd

    if os.get_blocking(master_fd):
        # If we write more than tty/ndisc is willing to buffer, we may block
        # indefinitely. So we set master_fd to non-blocking temporarily during
        # the copy operation.
        os.set_blocking(master_fd, False)
        try:
            _copy(master_fd, master_read, stdin_read, nei_read)
        finally:
            # restore blocking mode for backwards compatibility
            os.set_blocking(master_fd, True)
        return
    high_waterlevel = 4096
    stdin_avail = master_fd != STDIN_FILENO
    stdout_avail = master_fd != STDOUT_FILENO
    i_buf = b''
    o_buf = b''
    while 1:
        rfds = []
        wfds = []
        print(where, 'stdin_avail', stdin_avail, 'stdout_avail', stdout_avail, len(i_buf), len(o_buf))

        if stdin_avail and len(i_buf) < high_waterlevel:
            rfds.append(STDIN_FILENO)
        if stdout_avail and len(o_buf) < high_waterlevel:
            rfds.append(master_fd)
        if stdout_avail and len(o_buf) > 0:
            wfds.append(STDOUT_FILENO)
        if len(i_buf) > 0:
            wfds.append(master_fd)

        rfds.append(nei_fd)

        print(where, 'selecting')
        rfds, wfds, _xfds = select(rfds, wfds, [])
        print(where, 'selected')

        if STDOUT_FILENO in wfds:
            print(where, 'write out', o_buf)
            try:
                n = os.write(STDOUT_FILENO, o_buf)
                o_buf = o_buf[n:]
            except OSError:
                stdout_avail = False

        if master_fd in rfds:
            print(where, 'master_fd in rfds')
            # Some OSes signal EOF by returning an empty byte string,
            # some throw OSErrors.
            try:
            ## fuck: we should distinguish empty data
            ## because we swallowed marker from possible EOF
            ## fuck on real empty data we should return
                data, swallowed = master_read(master_fd)
            except OSError:
                print('fucking OSError')
                return    # Assume the child process has exited and is
                          # unreachable, so we clean up.
            o_buf += data

        if master_fd in wfds:
            print(where, 'master_fd in wfds')
            n = os.write(master_fd, i_buf)
            i_buf = i_buf[n:]

        if stdin_avail and STDIN_FILENO in rfds:
            print(where, 'read in')
            data, swallowed = stdin_read(STDIN_FILENO)
            ## fuck: we should distinguish empty data
            ## because we swallowed marker from possible EOF
            if not data and not swallowed:
                stdin_avail = False
            else:
                i_buf += data

        if nei_fd in rfds:
            print(where, 'nei_fd in rfds')
            piggy_data = _read(nei_fd)
            if not piggy_data:
                os.close(nei_fd)
                nei_fd = os.open(nei_fn, os.O_RDONLY or os.O_NONBLOCK)
            else:
                print(where, 'request to send', piggy_data)
                if local:
                    i_buf += b'_.oOO'
                    i_buf += piggy_data
                    i_buf += b'OOo._'
                else: # remote
                    o_buf += b'_.oOO'
                    o_buf += piggy_data
                    o_buf += b'OOo._'

if __name__ == "__main__":
    print('\n\n\n\n\n\n\n')
    local = True # are we the local transmission unit or the gegenstelle
    where = 'local '
    nei_fn  = '/tmp/nei'
    naus_fn = '/tmp/naus'

    if len(sys.argv) > 1:
        local = False
        where = 'remote'
        nei_fn  = '/tmp/nei_gegenstelle'
        naus_fn = '/tmp/naus_gegenstelle'

    ensure_fifo(naus_fn)
    ensure_fifo(nei_fn)

#     nei_thread = Thread(target = read_nei)
#     nei_thread.start()

    naus_thread = Thread(target = write_naus)
    naus_thread.start()

    spawn("/bin/bash", master_read, stdin_read)
#     spawn("/usr/local/bin/nvim", master_read, stdin_read)

    print('quitting')
    qquit = True

#     nei_thread.join()
    naus_thread.join()
