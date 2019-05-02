#!/usr/bin/env python

import ao
import mad
import readline
import socket
import struct
import sys
import threading
from time import sleep


total_num_of_data = 0
RECV_BUFFER_SIZE = 4096

QUEUE_LENGTH = 10
SEND_BUFFER = 4096
PAYLOAD_BUFFER_SIZE = 4000

MSG_STATUS_SUCCESS = '200'
MSG_STATUS_FAILURE = '404'
MSG_TYPE_LIST = '0'
MSG_TYPE_PLAY = '1'
MSG_TYPE_STOP = '2'

STATE_NOT_PROCESSED = '0'
STATE_PROCESSING = '1'
STATE_DONE_PROCESSING = '2'

song_playing_index = -1


def msg_parser(data):

    count = 0
    status = data[1:4]
    session_id = data[6:9]
    msg_type = data[11:12]
    length_of_payload_str = data[14:18]
    num_start = 0
    for ch in length_of_payload_str:
        if ch == '0':
            num_start += 1
        else:
            break
    length_of_payload = int(length_of_payload_str[num_start:])

    content = data[20:len(data)-1]
    return status, session_id, length_of_payload, msg_type, content


# The Mad audio library we're using expects to be given a file object, but
# we're not dealing with files, we're reading audio data over the network.  We
# use this object to trick it.  All it really wants from the file object is the
# read() method, so we create this wrapper with a read() method for it to
# call, and it won't know the difference.
# NOTE: You probably don't need to modify this class.
class mywrapper(object):
    def __init__(self):
        self.mf = None
        self.data = ""

    # When it asks to read a specific size, give it that many bytes, and
    # update our remaining data.
    def read(self, size):
        result = self.data[:size]
        self.data = self.data[size:]
        return result


# def list_play_packet_thread_func(wrap, cond_filled, sock):
# Receive messages.  If they're responses to info/list, print
# the results for the user to see.  If they contain song data, the
# data needs to be added to the wrapper object.  Be sure to protect
# the wrapper with synchronization, since the other thread is using
# it too!
def song_recv_thread_func(wrap, cond_filled, sock):
    while True:
        # TODO::What if the content itself has brackets? maybe force to count till last
        # bracket?

        data = sock.recv(4021)
        # print("===incoming length check===")
        # print(len(data))
        # print("===incoming length check===")
        # print(data[0:30])
        # count = 0
        # count_debug = 0
        status, song_id, length_of_payload, msg_type, content = msg_parser(
            data)

        if song_id != song_playing_index:
            continue

        while length_of_payload > len(data):
            print("inside loop")
            data += sock.recv(RECV_BUFFER_SIZE)
        if msg_type == MSG_TYPE_PLAY:
            cond_filled.acquire()
            if wrap.data == None:
                wrap.data = content
            else:
                wrap.data += content

            cond_filled.notify()
            cond_filled.release()
        else:
            print("Wrong response for the [play] or [stop] request.")


# If there is song data stored in the wrapper object, play it!
# Otherwise, wait until there is.  Be sure to protect your accesses
# to the wrapper with synchronization, since the other thread is
# using it too!
def song_play_thread_func(wrap, cond_filled, dev):
    while True:
        """
        TODO
        example usage of dev and wrap (see mp3-example.py for a full example):
        buf = wrap.mf.read()
        dev.play(buffer(buf), len(buf))
        """
        cond_filled.acquire()
        while wrap.data == None or len(wrap.data) == 0:
            cond_filled.wait()

        wrap.mf = mad.MadFile(wrap)
        while True:
            buf = wrap.mf.read()
            if buf is None:
                break
            dev.play(buffer(buf), len(buf))

        cond_filled.release()


def list_thread_func(sock):
    while True:
        data = sock.recv(4021)
        status, session_id, length_of_payload, msg_type, content = msg_parser(
            data)

        while length_of_payload > len(data):
            print("inside loop")
            data += sock.recv(RECV_BUFFER_SIZE)

        # if msg_type == MSG_TYPE_LIST:
        print(content)
        # else:
        # print("Wrong response for the [list] request.")


def main():
    if len(sys.argv) < 3:
        print 'Usage: %s <server name/ip> <server port>' % sys.argv[0]
        sys.exit(1)

    # Create a pseudo-file wrapper, condition variable, and socket.  These will
    # be passed to the thread we're about to create.
    wrap = mywrapper()

    # Create a condition variable to synchronize the receiver and player threads.
    # In python, this implicitly creates a mutex lock too.
    # See: https://docs.python.org/2/library/threading.html#condition-objects
    cond_filled = threading.Condition()

    # Create 2 TCP sockets and try connecting to the server.
    # One for play/stop, and the other for list.
    sock_play = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_play.connect((sys.argv[1], int(sys.argv[2])))
    sock_list = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_list.connect((sys.argv[1], int(sys.argv[2])))

    # Create a thread whose job is to receive play / stop responses from the server.
    song_recv_thread = threading.Thread(
        target=song_recv_thread_func,
        args=(wrap, cond_filled, sock_play)
    )
    song_recv_thread.daemon = True
    song_recv_thread.start()

    # Create a thread whose job is to receive list responses from the server.
    list_thread = threading.Thread(
        target=list_thread_func,
        args=(sock_list,)
    )
    list_thread.daemon = True
    list_thread.start()

    # Create a thread whose job is to play audio file data.
    dev = ao.AudioDevice('pulse')
    song_play_thread = threading.Thread(
        target=song_play_thread_func,
        args=(wrap, cond_filled, dev)
    )
    song_play_thread.daemon = True
    song_play_thread.start()

    # Enter our never-ending user I/O loop.  Because we imported the readline
    # module above, raw_input gives us nice shell-like behavior (up-arrow to
    # go backwards, etc.).
    while True:
        line = raw_input('>> ')

        if ' ' in line:
            cmd, args = line.split(' ', 1)
            try:
                int(args)
            except ValueError:
                print("invalid song id")
                continue
        else:
            cmd = line

        # TODO: Send messages to the server when the user types things.
        if cmd in ['l', 'list']:
            sock_list.sendall(line)

        if cmd in ['p', 'play']:
            sock_play.sendall(line)
            global song_playing_index
            song_playing_index = int(args)
            # clear song buffer

        if cmd in ['s', 'stop']:
            sock_play.sendall(line)
            # clear song buffer

        if cmd in ['quit', 'q', 'exit']:
            print("Bye bye!")
            sys.exit(0)


if __name__ == '__main__':
    main()
