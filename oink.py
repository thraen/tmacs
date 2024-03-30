#!/usr/bin/env python3

import os
import mypty
import tty
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

Qnei  = queue.Queue()
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
    print('reading', arr.decode(), 'holding', hold.decode())
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

def stdin_read(fd):
    data = os.read(fd, 1024)
#     blastdin.write(data) 
#     blastdin.flush()
    return data

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

    dat = os.read(fd, 1024)

#     blamaster.write(dat) 
#     blamaster.flush()

    ret = do_oink(dat)
#     for i, dati in enumerate(dat):
#         reti = ret[i]
#         if reti != dati:
#             print('dif', i,dati,reti,dat[i-1], ret[i-1])
#     print(len(ret), len(dat))

    return ret

def read_nei():
    global qquit
    global Qnei
    fd = open('/tmp/nei', 'r')
    while not qquit:
        data = fd.read()
        if not data:  # EOF is reached
            print("nei: EOF, reopen")
            fd.close()
            fd = open('/tmp/nei', 'r')
        else:
            Qnei.put(data)
            print("nei :", data)
    print('nei: -> quit')
    fd.close()
#     os.remove('/tmp/nei')

def write_naus():
    global qquit
    global Qnaus
    print('enter naus: get Qnaus')
    while not qquit:
        print('naus: get Qnaus')
        x = Qnaus.get()
        fd = open('/tmp/naus', 'w')
        fd.write(x.decode())
        fd.close()
        print('naus:', x)

    print('naus: -> quit')
#     os.remove('/tmp/naus')

if __name__ == "__main__":
    print('\n\n\n\n')
    ensure_fifo('/tmp/naus'+os.getpid())
    ensure_fifo('/tmp/nei'+os.getpid())

#     nei_thread = Thread(target = read_nei)
#     nei_thread.start()

    naus_thread = Thread(target = write_naus)
    naus_thread.start()

    mypty.spawn("/bin/zsh", master_read, stdin_read)
#     mypty.spawn("/usr/local/bin/nvim", master_read, stdin_read)

    print('quitting')
    qquit = True

#     nei_thread.join()
    naus_thread.join()
