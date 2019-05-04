#!/usr/bin/env python

import os
import socket
import struct
import sys
from threading import Lock, Thread


QUEUE_LENGTH = 10
SEND_BUFFER = 4096
PAYLOAD_BUFFER_SIZE = 4000
RECV_BUFFER_SIZE = 32

MSG_STATUS_SUCCESS = '200'
MSG_STATUS_FAILURE = '404'
MSG_TYPE_LIST = '0'
MSG_TYPE_PLAY = '1'
MSG_TYPE_STOP = '2'

STATE_INIT = 0
STATE_LIST = 1
STATE_LIST_DONE = 2
STATE_PLAY = 3
STATE_PLAY_DONE = 4
STATE_PLAY_ANOTHER = 5
STATE_STOP = 6
STATE_STOP_DONE = 7

songs = ""
songlist = []
music_dir = ""


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
        self.state = STATE_INIT
        self.count_of_play = 0
        print("[Client {0}] Connects in".format(self.session_id))


# Thread that sends music and lists to the client.  All send() calls
# should be contained in this function.  Control signals from client_read could
# be passed to this thread through the associated Client object.  Make sure you
# use locks or similar synchronization tools to ensure that the two threads play
# nice with one another!
def client_write(client):
    while True:
        # close connection is the client disconnects
        if client.alive == False:
            print("[Client {0}] Closes connection".format(client.session_id))
            break
        # busy loop when the client first connects in with no cmd
        if client.state == STATE_INIT:
            continue
        elif client.state == STATE_PLAY_DONE or client.state == STATE_STOP_DONE or client.state == STATE_LIST_DONE:
            continue
        else:
            send_status = send_response_to_client(client)
            if send_status < 0:
                break
    client.conn.close()


def send_response_to_client(client):
    message = ""
    payload = ""
    if client.cmd in ["list", "l"]:
        payload = songs
        message = "[%s][%s][%s][%04d][%s]" % (
            MSG_STATUS_SUCCESS, client.session_id, MSG_TYPE_LIST, len(payload), payload)
        sendall_wrapper(client, message)
        set_state_for_client(client, STATE_LIST_DONE)
    elif client.cmd in ["play", "p"]:
        print("[Client {0}] Will send play {1} msg in write thread".format(
            client.session_id, client.optional_arg))
        # song index does not exist
        if client.optional_arg < 0:
            message = "[%s][%s][%s][%04d][%s]" % (
                MSG_STATUS_FAILURE, client.session_id, MSG_TYPE_PLAY, len(payload), payload)
            sendall_wrapper(client, message)
            set_state_for_client(client, STATE_PLAY_DONE)
            return 1
        # song index is invalid
        song_index = client.optional_arg
        if song_index >= len(songlist):
            message = "[%s][%s][%s][%04d][%s]" % (
                MSG_STATUS_FAILURE, client.session_id, MSG_TYPE_PLAY, len(payload), payload)
            sendall_wrapper(client, message)
            set_state_for_client(client, STATE_PLAY_DONE)
            return 1
        # retrieve song content and send in a series of packets
        filename = songlist[song_index] + '.mp3'
        f = open(music_dir + '/' + filename, 'rb')
        total_num_of_bytes_read = 0
        bytes_read = f.read(PAYLOAD_BUFFER_SIZE)
        count_read = 0

        while (len(bytes_read) > 0):
            count_read += 1
            total_num_of_bytes_read += len(bytes_read)
            payload = bytes_read
            message = "[%s][%03d][%s][%04d][%s]" % (
                MSG_STATUS_SUCCESS, client.count_of_play, MSG_TYPE_PLAY, len(payload), payload)
            # client interrupt by [stop]
            if not client.alive:
                print("[Client {0}] Not alive".format(client.session_id))
                break
            if client.state == STATE_STOP:
                print("[Client {0}] Stops streaming due to [stop] command in write thread".format(
                    client.session_id))
                f.close()
                return 1
            if client.state == STATE_PLAY_ANOTHER:
                print("[Client {0}] Requests to play another song: {1} in write thread".format(
                    client.session_id, client.optional_arg))
                f.close()
                set_state_for_client(client, STATE_PLAY)
                return 1
            message_sent_status = sendall_wrapper(client, message)
            if message_sent_status < 0:
                set_state_for_client(client, STATE_PLAY_DONE)
                return -1
            f.seek(total_num_of_bytes_read)
            bytes_read = f.read(PAYLOAD_BUFFER_SIZE)
        print("[Client {0}] Done sending all stream packets for Song {1}!".format(
            client.session_id, client.optional_arg))
        f.close()
        set_state_for_client(client, STATE_PLAY_DONE)
    elif client.cmd in ["stop", "s"]:
        print("[Client {0}] Will send stop msg in write thread".format(
            client.session_id))
        message = "[%s][%03d][%s][%04d][%s]" % (
            MSG_STATUS_SUCCESS, client.count_of_play, MSG_TYPE_STOP, len(payload), payload)
        sendall_wrapper(client, message)
        set_state_for_client(client, STATE_STOP_DONE)
    else:
        print("[Client {0}] Should not reach here [2]".format(
            client.session_id))
    return 1


# send message while catching IO error for client closes connection
def sendall_wrapper(client, message):
    try:
        client.conn.sendall(message)
        return 1
    except IOError:
        print("[Client {0}] Failed to send packets due to connection closed".format(
            client.session_id))
        return -1


# Thread that receives commands from the client.  All recv() calls should
# be contained in this function.
def client_read(client):
    while True:
        try:
            line = client.conn.recv(RECV_BUFFER_SIZE)
        except IOError:
            client.lock.acquire()
            try:
                client.alive = False
            finally:
                client.lock.release()
            break
        print("[Client {0}] Requests [{1}]".format(client.session_id, line))
        if not line or line.decode('utf-8') == 'quit':
            client.lock.acquire()
            try:
                client.alive = False
            finally:
                client.lock.release()
            break
        # store cmd and args in client instance
        if ' ' in line:
            cmd, args = line.split(' ', 1)
        else:
            cmd = line
        # if the cmd is not valid, then go to next round
        if not is_valid_command(cmd):
            continue
        # set client state
        client.lock.acquire()
        try:
            if cmd in ["play", "p"]:
                client.optional_arg = int(args)
                client.count_of_play = client.count_of_play + 1
                # at this moment client is streaming [play] packets
                if client.state == STATE_PLAY:
                    client.state = STATE_PLAY_ANOTHER
                    print("[Client {0}] Requests to play another song: {1} in read thread".format(
                        client.session_id, client.optional_arg))
                else:
                    client.state = STATE_PLAY
            elif cmd in ["stop", "s"]:
                print("[Client {0}] Requests to stop in read thread".format(
                    client.session_id))
                client.count_of_play = client.count_of_play + 1
                client.state = STATE_STOP
            elif cmd in ["list", "l"]:
                client.state = STATE_LIST
            else:
                print("[Client {0}] Should not reach here. [1]".format(
                    client.session_id))
            client.cmd = cmd
        finally:
            client.lock.release()
    # print("[Client {0}] Disconnects".format(client.session_id))


def is_valid_command(cmd):
    if cmd in ["list", "l", "play", "p", "stop", "s"]:
        return True
    return False


def set_state_for_client(client, state):
    client.lock.acquire()
    try:
        client.state = state
    finally:
        client.lock.release()


def get_mp3s(musicdir):
    print("Reading music files...")
    global music_dir
    music_dir = musicdir
    songs_temp = []
    songs_temp.append("\n")
    for filename in os.listdir(musicdir):
        if not filename.endswith(".mp3"):
            continue
        # Store song metadata for future use.  You may also want to build
        # the song list once and send to any clients that need it.
        print("Found {0} {1}".format(len(songlist), filename))
        # store song name and index in "songlist"
        songs_temp.append("{0}. {1}\n".format(len(songlist), filename[:-4]))
        songlist.append("{0}".format(filename[:-4]))
    songs_temp.append(">> ")

    songs = "".join(songs_temp)
    # songs = songs[:-1]
    print("Found {0} song(s)!".format(len(songlist)))
    return [songs, songlist]


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python server.py [port] [musicdir]")
    if not os.path.isdir(sys.argv[2]):
        sys.exit("Directory '{0}' does not exist".format(sys.argv[2]))

    port = int(sys.argv[1])
    global songs, songlist
    songs, songlist = get_mp3s(sys.argv[2])
    threads = []
    session_id = 1

    # create a socket and accept incoming connections
    # open socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    except socket.error as err:
        print "Socket creation failed with error %s" % (err)

    # bind server port to socket
    s.bind(('', port))
    s.listen(QUEUE_LENGTH)

    while True:
        client_conn, client_addr = s.accept()
        client = Client(client_conn, client_addr, session_id)
        session_id += 1
        t = Thread(target=client_read, args=(client,))
        threads.append(t)
        t.start()
        t = Thread(target=client_write, args=(client,))
        threads.append(t)
        t.start()

    s.close()


if __name__ == "__main__":
    main()
