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
import queue #fuck use select
from threading import Thread # fuck use select

import inspect

log = open('/tmp/oinklog', 'a')
oprint = print
def print(*args):
    oprint(*args, file = log)
    log.flush()

start_marker = b"\x1F_.o"+ b"OO"
end_marker = b"\x1FOO" + b"o._"
# start_marker = b"_.o"+ b"OO"
# end_marker = b"OO" + b"o._"
clip_marker = b"C"

hold = bytearray(b'')

piggy = bytearray(b'')

marker = start_marker
j = 0

qquit = False

active = False

def alternate_marker(marker):
    if marker == start_marker:
        return end_marker
    else:
        return start_marker

# Qraus = queue.Queue()


def piggy_end():
    global piggy
    print(where, 'piggy_end', piggy)
#     Qraus.put(piggy)

    ## the fifo blocks, if nothing reads from it.
    #     fd = open(raus_fn, 'w')
    #     fd.write(piggy.decode('utf-8'))
    #     fd.close()

    if local:
        import subprocess
        print(where, 'calling xclip with', piggy)
#         clipcmdv = "xclip -i -r -selection PRIMARY".split(' ')
        clipcmdv = "xclip -i -selection PRIMARY".split(' ')

        p = subprocess.Popen(clipcmdv, stdin=subprocess.PIPE)
        p.communicate(input= piggy)[0]
    else:
        print(where, 'print write to lastclip', piggy)
        with open("/tmp/lastclip", 'wb') as lastclipf:
            lastclipf.write(piggy)

#     if piggy.startswith(start_marker + clip_marker):
#         print('clipboard marker read, setting clipboard')
#         offset = len(start_marker) + len(clip_marker)
#         clipb = piggy[offset:]
#         os.system("xclip -i -r -selection PRIMARY", + clipb.decode('utf-8'))
#         with fopen("/tmp/lastclip", 'wb') as lastclipf:
#             lastclipf.write(clipb)


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

termsize = ()
def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

## Remoteward we piggyback on stdin, localward we piggyback on stdout
## It means for master_read: 
## * when we run locally  -> master_read looks for piggy data
## * when we run remotely -> master_read is transparent
def master_read(fd):
    global termsize

    ts = os.get_terminal_size()
    if (ts != termsize):
        termsize = ts
        set_winsize(fd, termsize[1], termsize[0])

    data = os.read(fd, 1024)

    print(where,'master_read', data)
    ## If the gegenstelle is not running and thus not 
    ## supressing markers, local echo from bash will arrive here.
    ## We only want it to arrive at remote stdout, not here.
    ## So we only start interpreting markers from stdout if gegenstelle
    ## has been started (active = true)
    if local and active:
        ret = do_oink(data)
        swallowed = len(data) > 0 and len(ret) == 0
        return ret, swallowed
    else:
        return data, False

def write_raus():
    global Qraus
    print('enter raus: get Qraus')
    while not qquit:
        print('raus: get Qraus')
        x = Qraus.get()
        fd = open(raus_fn, 'w')
        fd.write(x.decode())
        fd.close()
        print('raus:', x)

    print('raus: -> quit')
#     os.remove(raus_fn)


STDIN_FILENO = 0
STDOUT_FILENO = 1
STDERR_FILENO = 2

CHILD = 0

rein_fd = None

def spawn(argv, master_read, stdin_read):
    print('spawn', argv[0], argv)
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

    global rein_fd
    rein_fd = os.open(rein_fn, os.O_RDONLY or os.O_NONBLOCK)

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

def getchar():
    #Returns a single character from standard input
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.buffer.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

## Remoteward we piggyback on stdin, localward we piggyback on stdout
## It means for stdin_read: 
## * we run remotely ->  stdin_read looks out for piggy data
## * we run locally  ->  stdin_read is transparent
def stdin_read(fd):
    data = os.read(fd, 1024)

    print(where, 'stdin_read', data)
    if local:
        if (data == b'\x02'):  # C-b ## todo better listen to controlling fifo
            global active
            active = True
            next_char = getchar()
            if (next_char == b'\x02'): 
                return b'\x02', False
            if (next_char == b'b'):
                the_source = inspect.getsource(sys.modules[__name__])
                tmp = "stty -echo\n HISTCONTROL=ignoreboth echo " + shlex.quote(the_source) + "> /tmp/oink.py; chmod a+x /tmp/oink.py; stty echo\n /tmp/oink.py gegenstelle\n"
                return tmp.encode("utf-8"), False

            return b'\x02'+next_char, False

        return data, False
    else:
        ret = do_oink(data)
        swallowed = len(data) > 0 and len(ret) == 0
        return ret, swallowed

def _copy(master_fd, master_read, stdin_read, rein_read):
    """Parent copy loop.
    Copies
            pty master -> standard output   (master_read)
            standard input -> pty master    (stdin_read)"""

    global rein_fd

    if os.get_blocking(master_fd):
        # If we write more than tty/ndisc is willing to buffer, we may block
        # indefinitely. So we set master_fd to non-blocking temporarily during
        # the copy operation.
        os.set_blocking(master_fd, False)
        try:
            _copy(master_fd, master_read, stdin_read, rein_read)
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

        rfds.append(rein_fd)

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
                ## we should distinguish empty data because of swallowed 
                ## from possible EOF
                data, swallowed = master_read(master_fd)
                if not data and not swallowed:
                    return
            except OSError:
                print('OSError out')
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

            ## we distinguish empty data because of swallowed 
            ## from possible EOF 
            if not data and not swallowed: # naturally occuring EOF
                stdin_avail = False
            else:
                i_buf += data

        if rein_fd in rfds:
            print(where, 'rein_fd in rfds')
            piggy_data = _read(rein_fd)
            if not piggy_data:
                os.close(rein_fd)
                rein_fd = os.open(rein_fn, os.O_RDONLY or os.O_NONBLOCK)
            else:
                print(where, 'request to send', piggy_data)
                if local:
                    if active:
                        i_buf += start_marker + piggy_data + end_marker
                else: # remote
                    o_buf += start_marker + piggy_data + end_marker

if __name__ == "__main__":
    print('\n\n\n\n\n\n\n')
    local = True # are we the local transmission unit 
                 # or the remote gegenstelle
    where = 'local '
    rein_fn  = '/tmp/rein'
    raus_fn = '/tmp/raus'

    if len(sys.argv) > 1:
        local = False
        where = 'remote'
        rein_fn = '/tmp/rein_gegenstelle'
        raus_fn = '/tmp/raus_gegenstelle'

    ensure_fifo(raus_fn)
    ensure_fifo(rein_fn)

#     raus_thread = Thread(target = write_raus)
#     raus_thread.start()

    cmdv = "/bin/bash --rcfile ~/.brc_thr".split(' ')
    spawn(cmdv, master_read, stdin_read)
#     spawn("/bin/bash", master_read, stdin_read)
#     spawn("/usr/local/bin/nvim", master_read, stdin_read)

    print('quitting')
    qquit = True

#     raus_thread.join()
