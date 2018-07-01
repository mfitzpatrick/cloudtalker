#!/usr/bin/env python3

import socket

def upload():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("127.0.0.1", 9000))
    s.send('{"segment":"pir.1529842538.0.ts"}'.encode())
    s.close()

upload()
