#!/usr/bin/env python3

import json
import socket
import sys
import threading
try:
    import RPi.GPIO as gpio
except ImportError:
    pass

class actuator(object):
    """
    This class acts as a simple actuator. It can be subclassed if required to give
    additional functionality.
    """
    def __init__(self, outputpin=None, inputpin=None):
        self.ispi = True if 'RPi.GPIO' in sys.modules else False
        self.outputpin = outputpin if isinstance(outputpin, int) else None
        self.inputpin = inputpin if isinstance(inputpin, int) else None
        if self.ispi and self.inputpin is not None:
            #set up interrupt callback for pin (active-high)
            gpio.setup(self.inputpin, gpio.IN, pull_up_down=gpio.PUD_DOWN)
            gpio.add_event_detect(self.inputpin, gpio.RISING, callback=self.event, bouncetime=300)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def event(self, channel):
        print("rising edge detected on GPIO %d" % (self.inputpin))
        print(channel)

    def activate(self):
        print("actuator activate")
        if self.ispi and self.outputpin:
            #set GPIO high
            gpio.output(self.outputpin, gpio.high)

    def deactivate(self):
        print("actuator deactivate")
        if self.ispi and self.outputpin:
            #set GPIO low
            gpio.output(self.outputpin, gpio.low)

class cmd_listener(object):
    """
    This is an example which will listen on a given input socket for a JSON command.
    When the command is received, it is processed and a predefined callback is called.
    """
    def __init__(self, inport=None, handler=None):
        """
        Arguments:
        inport: input datagram port to listen for command messages
        handler: object with activate, and deactivate functions defined for handling commands
        """
        try:
            self.inport = int(inport)
        except:
            self.inport = None
        self.insock = None
        self.handler = handler

    def __enter__(self):
        """
        If specified, create a socket with the previously-presented port number. Then,
        start this class in a new thread that listens on the newly-created socket
        for incoming messages.
        """
        if self.inport is not None:
            self.insock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.insock.bind(('', self.inport))
            return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Close the socket created with __enter__() and stop any thread that has been started.
        """
        if self.insock:
            self.insock.close()
            self.insock = None

    def run(self):
        if self.insock is None:
            print("cmd_listener should be run using the 'with' statment!")
            return
        while True:
            data, addr = self.insock.recvfrom(1024)
            js = json.loads(data.decode('utf-8'))
            print("received JSON:", js)
            if self.handler and "command" in js:
                if js["command"] == "arm":
                    self.handler.activate()
                elif js["command"] == "disarm":
                    self.handler.deactivate()

if __name__ == "__main__":
    def get_args():
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument('-o', '--outport', default=9000,
            help="Output port, for seinding outgoing signals")
        parser.add_argument('-i', '--inport', default=9001,
            help="Input port, for receiving commands")
        return parser.parse_args()

    args = get_args()
    with actuator() as a:
        with cmd_listener(inport=args.inport, handler=a) as listener:
            listener.run()
