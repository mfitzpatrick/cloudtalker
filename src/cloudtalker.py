#!/usr/bin/env python3

import websocket
import ssl
import json
import os
import time
try:
    import thread
except ImportError:
    import _thread as thread

# BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def readFileChunks(f, chunk_size=1024):
    """
    Read a file one chunk at a time, returning each chunk
    """
    while True:
        data = f.read(chunk_size)
        if data: yield data
        else: return #no more data in file

class upload():
    def __init__(self, ctalker):
        self.ctalker = ctalker

    def uploadOneFile(self, fpath, isMotionTriggered=False):
        trigger_time = os.path.getmtime(fpath) #use file last-modified timestamp
        trigger_type = "pir" if isMotionTriggered else "request"
        self.ctalker.send("{\"type\":\"capture_start\",\"trigger_timestamp\":%d,"
            "\"trigger\":\"%s\"}" %
            (trigger_time, trigger_type))
        self.ctalker.send("{\"type\":\"capture_segment\",\"trigger_timestamp\":%d,"
            "\"trigger\":\"%s\",\"seg_no\":0}" %
            (trigger_time, trigger_type))
        with open(fpath, "rb") as f:
            for data in readFileChunks(f, chunk_size=1300):
                self.ctalker.send(data, isText=False)
        self.ctalker.send("{\"type\":\"capture_end\",\"trigger_timestamp\":%d,"
            "\"trigger\":\"%s\"}" %
            (trigger_time, trigger_type))

class cloudtalker():
    def __init__(self):
        self.isConnected = False

    def on_message(self, ws, message):
        print(message)
        self.send("{\"type\":\"state\", \"id\":2005, \"heartbeat_period\":55}")
        ## .loads returns a python dict object
        data = json.loads(message)
        for k,v in data.items():
            print("%s:%s" % (k, v)) # shows name and properties

    def on_error(self, ws, error):
        print(error)

    def on_close(self, ws):
        print("### closed ###")

    def on_open(self, ws):
        def run(*args):
            while True:
                print("state update")
                ws.send("{\"type\":\"state\", \"id\":2005, \"heartbeat_period\":10}")
                time.sleep(55 * 3)
        print("starting thread")
        thread.start_new_thread(run, ())
        print("thread started")

    def send(self, data, isText=True):
        """
        Wrap internal websocket-client data send
        """
        self.ws.send(data, opcode=websocket.ABNF.OPCODE_TEXT if isText else websocket.ABNF.OPCODE_BINARY)

    def connect(self, endpoint, cert, key):
        websocket.enableTrace(True)
        print("start wsapp")
        self.ws = websocket.WebSocketApp("wss://%s" % (endpoint),
            on_message = self.on_message,
            on_error = self.on_error,
            on_close = self.on_close,
            on_open = self.on_open)
        print("connected")
        self.isConnected = True
        self.ws.run_forever(ping_interval=55,
            sslopt={"cert_reqs": ssl.CERT_NONE,
                "ssl_version": ssl.PROTOCOL_TLSv1_2,
                "keyfile": key,
                "certfile": cert})


if __name__ == "__main__":
    def get_args():
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('-c', '--cert', default="cert.pem", help="Device public key (sold separately)")
        parser.add_argument('-k', '--key', default="key.pem", help="Device private key (sold separately)")

        #optional arguments
        parser.add_argument('-e', '--endpoint', default="ds.dsservers.net:8080/ds/v3", help="Specify a custom server endpoint")
        parser.add_argument('-f', '--filename', help="Video file name to upload")
        return parser.parse_args()

    print("app started now")
    #initialise serial ports and hardware
    args = get_args()
    print(os.path.dirname(os.path.realpath(__file__)))
    print(os.getcwd())

    ctalker = cloudtalker()
    if args.filename:
        def uploadTest(*threadargs):
            upl = upload(ctalker)
            time.sleep(5)
            while not ctalker.isConnected:
                print("uploadTest: waiting for connection...")
                time.sleep(10)
            upl.uploadOneFile(args.filename, isMotionTriggered=True)
        thread.start_new_thread(uploadTest, ())
    ctalker.connect(args.endpoint, args.cert, args.key)
    print("cloudConnect exited")


