#!/usr/bin/env python3

import socket
import json

def listen():
    port = 9001
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", port))
    print("socket is now listening on port %d..." % (port))
    while True:
        data, addr = s.recvfrom(1024)
        js = json.loads(data.decode('utf-8'))
        print("received JSON:", js)
    s.close()

listen()
