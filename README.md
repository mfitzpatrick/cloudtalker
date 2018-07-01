# cloudtalker
This app will connect to the cloud service via WebSocket,
authenticating with client certificates, and manage communication
with that service. The user can upload captured video files to the
cloud service, and access those videos with the service's mobile apps.

## Operation
For convenience, and for ease of initial setup and/or testing, this
is compatible with docker-compose.
To start:
```
docker-compose up
```

To end (after ctrl+c):
```
docker-compose down
```

## Interfacing
### Video file input
Applications wishing to interface with this app can do so by sending
JSON messages to a stream socket. In docker, the socket is localhost:9000.
Alternatively, if running natively you can use a unix socket instead
by specifying the `--input_sock` argument.

A single 'capture' can be made up of several separate video segment
files. Each segment file that is uploaded for a given contiguous capture
will be concatenated on the server and displayed as a single video file
in the app. A full capture is delineated by an opened and closed stream
connection.

The following python code is an example of how this can be done:
```
#a new capture has occurred, so open a new socket to send video files
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", 9000))

#send each segment file to be uploaded
s.send('{"segment":"pir.1529842538.0.mp4"}'.encode())
s.send('{"segment":"pir.1529842538.1.mp4"}'.encode())
s.send('{"segment":"pir.1529842538.2.mp4"}'.encode())
#...

#all video files have been reported to socket, so close connection
#to indicate no further files will be sent
s.close()
```

JSON format:
```
#filename format: <pir|cap>.<utc timestamp for whole capture>.<segment number>.mp4
{"segment": <full path string for video file>}
```

### Camera Command Messages
Periodically, the server may update the client with state changes or commands
that were initiated by the app. These may include 'arming' and 'disarming' the
motion detector (which should be a separate app), or requesting a fresh video
capture be undertaken and uploaded.

These messages can be forwarded from cloudtalker to a listening process via a
unix or inet datagram socket. Either use `--cam_sock /path/to/unix/sock` to
write to a unix datagram socket, or `--cam_addr 127.0.0.1:9000` to write to
an inet datagram socket.

This is the format of these datagram messages:
```
{"command": <"arm" | "disarm" | "capture">}
```
