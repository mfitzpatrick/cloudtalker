#!/usr/bin/env python3

import websocket
import ssl
import socket
import json
import os
import sys
import time
import datetime
import threading
import queue

def readFileChunks(f, chunk_size=1024):
    """
    Read a file one chunk at a time, returning each chunk
    """
    while True:
        data = f.read(chunk_size)
        if data: yield data
        else: return #no more data in file

def toInt(str):
    """
    Convert a string to an Integer and return it
    If not possible, return None.
    """
    try:
        port = int(str)
        return port
    except ValueError:
        return None

def split_inet_addr(addr):
    """
    Split INet addr into IP and port parts
    return (ip, port) tuple
    """
    split = addr.split(":")
    if len(split) < 2:
        return None
    ip = split[0]
    port = toInt(split[1])
    if port is None:
        return None
    return (ip, port)

class upload(threading.Thread):
    def __init__(self, ctalker):
        super(upload, self).__init__()
        self.ctalker = ctalker
        self.shouldStop = threading.Event()
        self.inq = queue.Queue()
        self.current_captype = None
        self.current_capts = None
        self.current_segno = None

    def init_capture(self):
        self.ctalker.send("{\"type\":\"capture_start\",\"trigger_timestamp\":%d,"
            "\"trigger\":\"%s\"}" % (self.current_capts, self.current_captype))

    def upload_one_file(self, fpath):
        self.ctalker.send("{\"type\":\"capture_segment\",\"trigger_timestamp\":%d,"
            "\"trigger\":\"%s\",\"seg_no\":%d}" %
            (self.current_capts, self.current_captype, self.current_segno))
        with open(fpath, "rb") as f:
            print("uploading file now...")
            for data in readFileChunks(f, chunk_size=1300):
                self.ctalker.send(data, isText=False)
            print("file upload completed")

    def end_capture(self):
        self.ctalker.send("{\"type\":\"capture_end\",\"trigger_timestamp\":%d,"
            "\"trigger\":\"%s\"}" % (self.current_capts, self.current_captype))
        #reset variables for later usage
        self.current_captype = self.current_capts = self.current_segno = None

    def join(self, timeout=None):
        """
        Thread join. Stop thread running.
        """
        self.shouldStop.set()
        self.inq.join()
        super(upload, self).join()

    def run(self):
        while not self.shouldStop.isSet():
            try:
                #file data dict
                fdata = self.inq.get(timeout=5)
                if fdata["path"] is not None:
                    print("uploading file", fdata["path"])
                    if self.current_capts is not None and self.current_capts != fdata["ts"]:
                        #There may be a capture currently running. Since this file doesn't
                        #match this capture, send end_capture so the server is sync'd
                        print("out of sync video sent!", self.current_capts, fdata["ts"])
                        self.end_capture()
                    #store so we can later send the capture_end message
                    self.current_captype = "pir" if fdata["type"] == "pir" else "request"
                    self.current_capts = fdata["ts"]
                    self.current_segno = fdata["segno"]
                    #upload file and finish
                    if self.current_segno == 0:
                        self.init_capture()
                    self.upload_one_file(fdata["path"])
                elif fdata["end_capture"] is not None:
                    self.end_capture()
                self.inq.task_done()
            except queue.Empty:
                pass #continue through loop and wait again if necessary

    def inspect_file(self, fpath, isMotionTriggered):
        self.current_captype = "pir" if isMotionTriggered else "cap"
        self.current_capts = os.path.getmtime(fpath) #use file last-modified timestamp
        self.current_segno = 0

    def parse_filename(self, fpath):
        """
        Attempt to parse filename to get capture type, capture timestamp, and segment num.
        FMT: <pir|cap>.<utc_ts>.<segno>.mp4
        Returns: Tuple ("pir"|"cap", <utc_ts>, <segno>) or None on error
        """
        fname = os.path.basename(fpath)
        if fname == "":
            return None
        parts = fname.split(".") #split on dot character
        print("parts are:", parts)
        if len(parts) >= 3 and (parts[0] == "pir" or parts[0] == "cap"):
            ts = int(parts[1])
            if ts == 0: #conversion likely failed
                return None
            segno = None
            try:
                segno = int(parts[2])
            except:
                return None
            return (parts[0], ts, segno)

    def add_file(self, fpath):
        """
        Add one file to be uploaded to the server.
        This function may be called from any thread
        """
        if not os.path.isfile(fpath):
            print("cloudtalker: cannot find file", fpath)
            return None
        #try to parse filename
        parsed = self.parse_filename(fpath)
        print("after parsing:", parsed)
        if parsed is not None:
            fdata = {
                "path": fpath,
                "type": parsed[0],
                "ts": parsed[1],
                "segno": parsed[2],
                "end_capture": None,
            }
            self.inq.put(fdata)
            print("upload module accepted file", fpath)

    def add_capture_end(self):
        """
        Indicate that no further segment files will be sent for the current capture.
        This concludes the capture upload to the server.
        """
        fdata = {
            "path": None,
            "end_capture": True,
        }
        self.inq.put(fdata)

class motionUploadManager(threading.Thread):
    """
    Manages the video file uploader by listening on input sockets and forwarding
    received video capture files to the uploading thread.
    Also manages the armed-state of the camera (and reports the armed-state to the
    video capture process via another socket).
    """
    def __init__(self, upload=None, motion_file_list=None, insock=None, cmdsock=None,
            inport=None, cmdaddr=None):
        super(motionUploadManager, self).__init__()
        self.upload = upload
        self.motion_file_list = motion_file_list
        self.insock = None
        self.isarmed = threading.Event()
        self.cmdsock = None
        #open new dgram socket for sending commands and updates
        if cmdsock:
            self.cmdsock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.cmdsock.connect(cmdsock)
        elif cmdaddr:
            addr_tuple = split_inet_addr(cmdaddr)
            if addr_tuple:
                self.cmdsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.cmdsock.connect(addr_tuple)
        #start listening on a socket for incoming messages containing files to upload
        if insock:
            self.insock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.insock.bind(insock)
        elif inport:
            port = toInt(inport)
            if port is not None:
                self.insock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.insock.bind(("", port))

    def __del__(self):
        if self.cmdsock:
            self.cmdsock.close()
            self.cmdsock = None
        if self.insock:
            self.insock.close()
            self.insock = None

    def __enter__(self):
        """
        Including this function means you can use this class with the python
        'with' statement, so internal objects are always cleaned up.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__del__()

    def set_upload_object(self, upload):
        """
        If the upload object can't be set at init time, it MUST be set here.
        """
        self.upload = upload

    def arm(self):
        """
        Camera is armed and can receive motion-triggered videos.
        """
        self.isarmed.set()
        if self.cmdsock:
            self.cmdsock.send('{"command":"arm"}'.encode())

    def disarm(self):
        """
        Camera is disarmed and should reject all motion-triggered videos.
        """
        self.isarmed.clear()
        if self.cmdsock:
            self.cmdsock.send('{"command":"disarm"}'.encode())

    def capture(self):
        """
        User has requested a single video capture regardless of whether there is motion.
        """
        if self.cmdsock:
            self.cmdsock.send('{"command":"capture"}'.encode())

    def listensock(self):
        """
        Open a listening UNIX socket and wait for a connection. Clients can send JSON
        data in the correct format indicating a number of segment files.
        When the connection is closed, the capture is deemed concluded.
        """
        while True:
            self.insock.listen(1)
            conn, addr = self.insock.accept()
            while True:
                data = conn.recv(1024)
                if data:
                    print("socket listener json", data.decode("utf-8"))
                    #parse and inspect JSON
                    js = json.loads(data.decode('utf-8'))
                    if "segment" in js:
                        if self.upload:
                            self.upload.add_file(js["segment"])
                else:
                    break
            print("recv data is None, close conn...")
            conn.close()
            if self.upload:
                self.upload.add_capture_end()

    def read_and_upload(self, f):
        for fpath in f:
            fpath = fpath.strip()
            # forward the file to the server if we are armed
            if self.isarmed.is_set():
                if self.upload:
                    self.upload.add_file(fpath)

    def run(self):
        """
        Choose input path: UNIX socket (preferred), sys.stdin, or named pipe.
        """
        print("motion upl mgr running")
        if self.motion_file_list == "-":
            # use stdin instead of a named file
            return readAndUpload(sys.stdin)
        elif self.insock is not None:
            return self.listensock()
        elif self.motion_file_list is not None:
            with open(self.motion_file_list, 'r') as f:
                self.read_and_upload(f)
        print("motionUploadManager has exited!")


class state():
    """
    State is stored as a dictionary of <string>:tuple(<val>, <lastUpdateTimestamp>).
    The accessor method, state["key"], will return only the 'val' part of the tuple. If
    you require the timestamp, use getUpdateTimeWithKey(key).
    """
    def __init__(self):
        self.lock = threading.RLock()
        self.lastRxMsg = None
        self.lastUpdateTime = time.time()
        self.state = {
            "id": (0, self.lastUpdateTime),
            "heartbeat_period": (10, self.lastUpdateTime),
            "pir_armed": (False, self.lastUpdateTime),
            "capture_asap": (False, self.lastUpdateTime),
        }

    def __getitem__(self, arg):
        """
        Standard method. Allows class to be called with square brackets.
        Returns value for given key argument
        i.e. state["id"] returns self.state["id"]
        """
        with self.lock:
            return self.state[arg][0]

    def __setitem__(self, key, val):
        """
        Opposite to __getitem__ (sets a value)
        """
        with self.lock:
            self.state[key] = (val, time.time())

    def getUpdateTimeWithKey(self, key):
        """
        Return the timestamp recorded for when this key's value was last updated.
        """
        with self.lock:
            return self.state[key][1]

    def getLastRxValWithKey(self, key):
        """
        Read value from the last-received dict using provided key.
        """
        with self.lock:
            if key in self.lastRxMsg:
                return self.lastRxMsg[key]
            else:
                return None

    def process(self, input):
        """
        Process input JSON data and store in internal state dict
        """
        with self.lock:
            # json.loads returns a python dict object
            data = json.loads(input)
            # add item to internal dict if it already exists
            self.lastUpdateTime = time.time()
            for k, v in data.items():
                if k in self.state:
                    if self.state[k][0] != v:
                        self.state[k] = (v, self.lastUpdateTime)
            # backup received dict in case it's needed later
            self.lastRxMsg = data

    def toJSON(self, addDict=None):
        """
        Return contents of internal state dict as JSON string
        """
        with self.lock:
            serialisedState = self.state.copy()
            if addDict:
                #Append addDict to state before serialising
                serialisedState.update(addDict)
            #remove timestamp from each value
            for k, v in serialisedState.items():
                if isinstance(serialisedState[k], tuple):
                    serialisedState[k] = v[0]
            return json.dumps(serialisedState, sort_keys=True)

class cloudtalker():
    """
    Manages WebSocket communication with cloud.
    Links each separate module together: state receiving, state processing, file uploading.
    Regularly heartbeats with server to ensure state is correct and up to date.
    """
    def __init__(self, upload_mgr=None, state=state()):
        self.state = state
        self.upload = upload(ctalker=self)
        self.motion_upload_mgr = upload_mgr
        if self.motion_upload_mgr:
            self.motion_upload_mgr.set_upload_object(self.upload)
            self.motion_upload_mgr.start()

    def __enter__(self):
        """
        Including this function means you can use this class with the python
        'with' statement, so internal objects are always cleaned up.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.upload.is_alive():
            self.upload.join()
        if self.motion_upload_mgr.is_alive():
            self.motion_upload_mgr.join()

    def on_message(self, ws, message):
        print(message)
        self.state.process(message)
        self.send(self.state.toJSON(addDict={"type":"state"}))
        #now check for important changes
        updateTime = self.state.lastUpdateTime
        if self.state.getUpdateTimeWithKey("pir_armed") == updateTime:
            if self.motion_upload_mgr:
                if self.state["pir_armed"]:
                    self.motion_upload_mgr.arm()
                else:
                    self.motion_upload_mgr.disarm()
        if self.state.getUpdateTimeWithKey("capture_asap") == updateTime:
            if self.motion_upload_mgr:
                self.motion_upload_mgr.capture()

    def on_error(self, ws, error):
        print(error)

    def on_close(self, ws):
        print("### closed ###")

    def on_open(self, ws):
        def run():
            """Check server for state sync every 10 heartbeats"""
            while True:
                print("state update (heartbeat period %s)" % self.state["heartbeat_period"])
                self.send(self.state.toJSON(addDict={"type":"state"}))
                time.sleep(self.state["heartbeat_period"] * 10)
        t = threading.Thread(target=run)
        t.start()
        if self.upload:
            #start upload thread now
            print("starting upload thread now")
            self.upload.start()

    def send(self, data, isText=True):
        """
        Wrap internal websocket-client data send
        """
        if isText:
            print("WebSocket send:", data)
        self.ws.send(data, opcode=websocket.ABNF.OPCODE_TEXT if isText else websocket.ABNF.OPCODE_BINARY)

    def sendFile(self, fpath, isMotionTriggered):
        """
        Upload specified file to server.
        """
        self.upload.add_file(fpath)

    def connect(self, endpoint, cert, key):
        websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp("wss://%s" % (endpoint),
            on_message = self.on_message,
            on_error = self.on_error,
            on_close = self.on_close,
            on_open = self.on_open)
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
        parser.add_argument('-e', '--endpoint', default="ds.dsservers.net:8080/ds/v3",
            help="Specify a custom server endpoint")
        parser.add_argument('--motion_file_list', default=None,
            help="File containing the list of files to upload (as motion-detected files)")
        parser.add_argument('--input_sock', default=None,
            help="Input unix stream socket for receiving capture files")
        parser.add_argument('--input_port', default=None,
            help="Input INet stream port for receiving capture files")
        parser.add_argument('--cam_sock', default=None,
            help="Unix dgram socket to send commands to (i.e. arm|disarm|capture, etc.)")
        parser.add_argument('--cam_addr', default=None,
            help="INet dgram ip:port address to send commands to (i.e. arm|disarm|capture, etc.)")
        return parser.parse_args()

    print("app started now")
    #initialise serial ports and hardware
    args = get_args()
    print(os.path.dirname(os.path.realpath(__file__)))
    print(os.getcwd())

    with motionUploadManager(motion_file_list=args.motion_file_list,
            insock=args.input_sock, cmdsock=args.cam_sock,
            inport=args.input_port, cmdaddr=args.cam_addr) as mgr:
        with cloudtalker(upload_mgr=mgr) as ctalker:
            ctalker.connect(args.endpoint, args.cert, args.key)
            print("cloudConnect exited")


