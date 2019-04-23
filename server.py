#!/usr/bin/env python

import os
import socket
import struct
import sys
from threading import Lock, Thread


QUEUE_LENGTH = 10
SEND_BUFFER = 4096

MSG_STATUS_SUCCESS = '200'
MSG_STATUS_FAILURE = '404'
MSG_TYPE_LIST = '0'
MSG_TYPE_PLAY = '1'
MSG_TYPE_STOP = '2'

# per-client struct


class Client:
    def __init__(self, addr):
        self.lock = Lock()


# TODO: Thread that sends music and lists to the client.  All send() calls
# should be contained in this function.  Control signals from client_read could
# be passed to this thread through the associated Client object.  Make sure you
# use locks or similar synchronization tools to ensure that the two threads play
# nice with one another!
def client_write(client):

    # TODO: Thread that receives commands from the client.  All recv() calls should
    # be contained in this function.
    return


def client_read(client):
    # TODO:
    return


def get_mp3s(musicdir):
    print("Reading music files...")
    songs = []
    songlist = []

    for filename in os.listdir(musicdir):
        if not filename.endswith(".mp3"):
            continue

        # TODO: Store song metadata for future use.  You may also want to build
        # the song list once and send to any clients that need it.
        print("{0} {1}".format(len(songs), filename))

        # store song name and index in "songlist"
        # songlist example: 0.Beethoven
        songlist.append("{0}. {1}".format(len(songs), filename[:-4]))

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
    print(songlist)
    threads = []
    session_id = 0

    # TODO: create a socket and accept incoming connections
    # open socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except socket.error as err:
        print "socket creation failed with error %s" % (err)

    # # bind server port to socket
    # s.bind(('', port))
    # s.listen(QUEUE_LENGTH)

    # while True:
    #     client = Client()
    #     t = Thread(target=client_read, args=(client))
    #     threads.append(t)
    #     t.start()
    #     t = Thread(target=client_write, args=(client))
    #     threads.append(t)
    #     t.start()
    # s.close()


if __name__ == "__main__":
    main()