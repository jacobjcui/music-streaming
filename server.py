#!/usr/bin/env python

import os
import socket
import struct
import sys
from threading import Lock, Thread


QUEUE_LENGTH = 10
SEND_BUFFER = 4096
RECV_BUFFER_SIZE = 32

MSG_STATUS_SUCCESS = '200'
MSG_STATUS_FAILURE = '404'
MSG_TYPE_LIST = '0'
MSG_TYPE_PLAY = '1'
MSG_TYPE_STOP = '2'

STATE_NOT_PROCESSED = 0
STATE_PROCESSING = 1
STATE_DONE_PROCESSING = 2

songs = []
songlist = []


# per-client struct
class Client:
    def __init__(self, conn, addr, session_id):
        self.lock = Lock()
        self.conn = conn
        self.addr = addr
        self.session_id = "{0:0=3d}".format(session_id)  # convert to string
        self.cmd = ""
        self.optional_arg = -1
        self.alive = True
        self.state = STATE_NOT_PROCESSED

        print("Client {0} is connected".format(self.session_id))


# TODO: Thread that sends music and lists to the client.  All send() calls
# should be contained in this function.  Control signals from client_read could
# be passed to this thread through the associated Client object.  Make sure you
# use locks or similar synchronization tools to ensure that the two threads play
# nice with one another!
def client_write(client):
    while True:
        if client.alive == False:
            print("Closes connection with Client {0}".format(
                client.session_id))
            break
        if client.cmd == "":
            continue
        if client.state == STATE_DONE_PROCESSING:
            continue
        message = compose_response_to_client(client)
        client.conn.sendall(message)
        # set client state
        client.lock.acquire()
        try:
            client.state = STATE_DONE_PROCESSING
        finally:
            client.lock.release()

    client.conn.close()


def compose_response_to_client(client):
    message = ""
    payload = ""
    if client.cmd == "list":
        payload = "".join(songlist)
        payload = payload[:-1]
        message = "[%s][%s][%s][%d][%s]" % (
            MSG_STATUS_SUCCESS, client.session_id, MSG_TYPE_LIST, len(payload), payload)
    elif client.cmd == "play":
        return message
    elif client.cmd == "stop":
        message = "[%s][%s][%s][%d][%s]" % (
            MSG_STATUS_SUCCESS, client.session_id, MSG_TYPE_STOP, len(payload), payload)
    else:
        print("Invalid command [{0}] from Client {1}".format(
            client.cmd, client.session_id))

    print("[message]={0}".format(message))
    return message


# TODO: Thread that receives commands from the client.  All recv() calls should
# be contained in this function.
def client_read(client):
    while True:
        line = client.conn.recv(RECV_BUFFER_SIZE)
        print("Client {0} requests [{1}]".format(client.session_id, line))
        if not line or line.decode('utf-8') == 'quit':
            client.alive = False
            break
        # store cmd and args in client instance
        if ' ' in line:
            cmd, args = line.split(' ', 1)
            client.optional_arg = args
        else:
            cmd = line
        # if the cmd is not valid, then go to next round
        if not is_valid_command(cmd):
            continue
        # set client status
        client.lock.acquire()
        try:
            client.cmd = cmd
            client.state = STATE_NOT_PROCESSED
        finally:
            client.lock.release()

    print("Client {0} disconnects".format(client.session_id))


def is_valid_command(cmd):
    if cmd == "list" or cmd == "play" or cmd == "stop":
        return True
    return False


def get_mp3s(musicdir):
    print("Reading music files...")

    for filename in os.listdir(musicdir):
        if not filename.endswith(".mp3"):
            continue

        # TODO: Store song metadata for future use.  You may also want to build
        # the song list once and send to any clients that need it.
        print("Found {0} {1}".format(len(songs), filename))

        # store song name and index in "songlist"
        # songlist example: 0.Beethoven
        songlist.append("{0}. {1}\n".format(len(songs), filename[:-4]))

        # store song content in 'songs'
        f = open(musicdir + '/' + filename, 'rb')
        song_content = f.read()
        songs.append(song_content)

    print("Found {0} song(s)!".format(len(songs)))
    return [songs, songlist]


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python server.py [port] [musicdir]")
    if not os.path.isdir(sys.argv[2]):
        sys.exit("Directory '{0}' does not exist".format(sys.argv[2]))

    port = int(sys.argv[1])
    songs, songlist = get_mp3s(sys.argv[2])
    threads = []
    session_id = 1

    # TODO: create a socket and accept incoming connections
    # open socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error as err:
        print "socket creation failed with error %s" % (err)

    # bind server port to socket
    s.bind(('', port))
    s.listen(QUEUE_LENGTH)

    while True:
        # print("******0*******")
        client_conn, client_addr = s.accept()

        client = Client(client_conn, client_addr, session_id)
        session_id += 1

        # print("******1*******")
        t = Thread(target=client_read, args=(client,))
        threads.append(t)
        t.start()

        # print("******2*******")
        t = Thread(target=client_write, args=(client,))
        threads.append(t)
        t.start()

    s.close()


if __name__ == "__main__":
    main()
