#!/usr/bin/env python

import ao
import mad
import readline
import socket
import struct
import sys
import threading
from threading import Lock, Thread
from time import sleep
import time
import random


total_num_of_data = 0
RECV_BUFFER_SIZE = 4021

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

stop_lock = Lock()
count_of_play_lock = Lock()


# count of play commands to filter incoming packets
# increment when command is [play] or [stop]
count_of_play = 0
count_of_packet_for_curr_count_of_play = 0


def clear_play_buffer(cond_filled, wrap):
    cond_filled.acquire()
    wrap.data = ''
    wrap.mf = mad.MadFile(wrap)
    cond_filled.notify()
    cond_filled.release()


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
    if num_start == len(length_of_payload_str):
        num_start -= 1
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

       
        data = sock.recv(RECV_BUFFER_SIZE)

        length_of_payload_str = ''
        if data[0:5] == '[200]':
            length_of_payload_str = data[14:18]
            num_start = 0
            for ch in length_of_payload_str:
                if ch == '0':
                    num_start += 1
                else:
                    break
            if num_start == len(length_of_payload_str):
                num_start -= 1
        else:
            continue
        length_of_payload = 0
        if length_of_payload_str != '':
            length_of_payload = int(length_of_payload_str[num_start:])

        while len(data) < length_of_payload:
            data += sock.recv(1)

       
        status, number_of_songs_played, length_of_payload, msg_type, content = msg_parser(
            data)
        number_of_songs_played_int = int(number_of_songs_played)

        if number_of_songs_played_int != count_of_play:
            continue

        if stop_flag:
            continue

       

        if msg_type == MSG_TYPE_PLAY:
            cond_filled.acquire()
            if wrap.data == None:
                wrap.data = content
            else:
                wrap.data += content
            cond_filled.notify()
            cond_filled.release()
        elif msg_type == MSG_TYPE_STOP:
            a = 1
        else:
            print("Wrong response for the [play] or [stop] request.")


# If there is song data stored in the wrapper object, play it!
# Otherwise, wait until there is.  Be sure to protect your accesses
# to the wrapper with synchronization, since the other thread is
# using it too!
def song_play_thread_func(wrap, cond_filled, dev):
    while True:
        if (len(wrap.data) == 0):
            continue
        
        cond_filled.acquire()
        wrap.mf = mad.MadFile(wrap)
        cond_filled.release()
        while True:
            cond_filled.acquire()
            buf = wrap.mf.read()
            cond_filled.release()
            if stop_flag:
                buf = None
            if buf is None:
                break
            dev.play(buffer(buf), len(buf))
        

def list_thread_func(sock):
    while True:
        
        data = sock.recv(RECV_BUFFER_SIZE)
        
        status, session_id, length_of_payload, msg_type, content = msg_parser(
            data)
        while length_of_payload > len(data):
            data += sock.recv(RECV_BUFFER_SIZE)

        if msg_type == MSG_TYPE_LIST:
            sys.stdout.write(content)
            sys.stdout.flush()
            
            
        else:
            print("Wrong response for the [list] request.")


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

    global stop_flag
    stop_flag = False
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

    # count of play commands to filter incoming packets
    global count_of_play
    count_of_play = 0
    global count_of_packet_for_curr_count_of_play
    count_of_packet_for_curr_count_of_play = 0
   
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
            cmd = 'list'
            line = 'list'
            sock_list.sendall(line)

        if cmd in ['p', 'play']:
            cmd = 'play'
            line = 'play' + ' ' + args
            stop_flag = False
            clear_play_buffer(cond_filled, wrap)
            sock_play.sendall(line)
            global song_playing_index

            song_playing_index = int(args)
            count_of_play += 1
            count_of_packet_for_curr_count_of_play = 0

        if cmd in ['s', 'stop']:
            cmd = 'stop'
            line = 'stop'

            stop_flag = True
            clear_play_buffer(cond_filled, wrap)

            sock_play.sendall(line)
            count_of_play += 1
            count_of_packet_for_curr_count_of_play = 0
        if cmd in ['quit', 'q', 'exit']:
            print("Bye bye!")
            sys.exit(0)


if __name__ == '__main__':
    main()
