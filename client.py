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
RECV_BUFFER_SIZE = 32

MSG_STATUS_SUCCESS = '200'
MSG_STATUS_FAILURE = '404'
MSG_TYPE_LIST = '0'
MSG_TYPE_PLAY = '1'
MSG_TYPE_STOP = '2'

STATE_NOT_PROCESSED = '0'
STATE_PROCESSING = '1'
STATE_DONE_PROCESSING = '2'

def msg_parser(data):
    
    
    # print("=====0=======\n")
    # print(data)
    count = 0
    status = data[1:4]
    session_id = data[6:9]
    msg_type = data[11:12]
    length_of_payload_str = data[14:18]
    
    content = data[20:len(data)-1]
    # print("======1=======\n")
    # print(content)
    # print("======2=======\n")
    return status, session_id, length_of_payload_str, msg_type, content






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


# Receive messages.  If they're responses to info/list, print
# the results for the user to see.  If they contain song data, the
# data needs to be added to the wrapper object.  Be sure to protect
# the wrapper with synchronization, since the other thread is using
# it too!
def recv_thread_func(wrap, cond_filled, sock):
    while True:
        # TODO::What if the content itself has brackets? maybe force to count till last
        # bracket?
        data = sock.recv(RECV_BUFFER_SIZE)
        count = 0
        count_debug = 0
        while count < 5:
            count_debug += 1
            for c in data:
                if c == ']':
                    count += 1
                    
            data += sock.recv(RECV_BUFFER_SIZE)
        # print(count_debug)
        
        
        status, session_id, length_of_payload_str, msg_type, content = msg_parser(data)
        # print("message type")
        
        # print(msg_type)
        if msg_type == MSG_TYPE_LIST:
        #     print("yes")
             print(content)
        # else:
        #     print("not yet")
        # global total_num_of_data
        # total_num_of_data += len(data)
        # print(total_num_of_data)
        
        


# If there is song data stored in the wrapper object, play it!
# Otherwise, wait until there is.  Be sure to protect your accesses
# to the wrapper with synchronization, since the other thread is
# using it too!
def play_thread_func(wrap, cond_filled, dev):
    while True:
        """
        TODO
        example usage of dev and wrap (see mp3-example.py for a full example):
        buf = wrap.mf.read()
        dev.play(buffer(buf), len(buf))
        """
        # wrap.data = data
        # wrap.mf = mad.MadFile(wrap)
        # buf = wrap.mf.read()
        # dev.play(buffer(buf), len(buf))


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

    # Create a TCP socket and try connecting to the server.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((sys.argv[1], int(sys.argv[2])))

    # Create a thread whose job is to receive messages from the server.
    recv_thread = threading.Thread(
        target=recv_thread_func,
        args=(wrap, cond_filled, sock)
    )
    recv_thread.daemon = True
    recv_thread.start()

    # Create a thread whose job is to play audio file data.
    dev = ao.AudioDevice('pulse')
    play_thread = threading.Thread(
        target=play_thread_func,
        args=(wrap, cond_filled, dev)
    )
    play_thread.daemon = True
    play_thread.start()

    # Enter our never-ending user I/O loop.  Because we imported the readline
    # module above, raw_input gives us nice shell-like behavior (up-arrow to
    # go backwards, etc.).
    while True:
        line = raw_input('>> ')

        if ' ' in line:
            cmd, args = line.split(' ', 1)
        else:
            cmd = line

        # TODO: Send messages to the server when the user types things.
        global total_num_of_data
        total_num_of_data = 0
        sock.sendall(line)

        # if cmd in ['l', 'list']:
        #     print 'The user asked for list.'

        # if cmd in ['p', 'play']:
        #     print 'The user asked to play:', args

        # if cmd in ['s', 'stop']:
        #     print 'The user asked for stop.'

        if cmd in ['quit', 'q', 'exit']:
            sys.exit(0)


if __name__ == '__main__':
    main()
