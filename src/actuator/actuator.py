#!/usr/bin/env python3

import json
import socket
import sys
import threading
try:
    import RPi.GPIO as gpio
    gpio.setmode(gpio.BCM)
except ImportError:
    pass

def toint(str):
    try:
        return int(str)
    except ValueError:
        return None

class actuator(object):
    """
    This class acts as a simple actuator. It can be subclassed if required to give
    additional functionality.
    The input and output pins passed in are Raspberry Pi GPIO pins that this class needs
    to interact with. In response to calls to the activate() and deactivate() functions
    this class will drive the output GPIO pin. In response to rising changes on the input
    GPIO pin, this class will send an 'alarm' message to the cloud server.
    """
    def __init__(self, outputpin=None, inputpin=None, outaddr=None):
        """
        outputpin: GPIO pin to drive in response to activate() and deactivate() calls
        inputpin: input GPIO pin. When driven high, this class will interrupt and send
            an 'alarm' message to the cloud service
        outaddr: inet stream socket to send the 'alarm' message to (if required).
            NB: this MUST be in the form <host>:<port>
        """
        self.ispi = True if 'RPi.GPIO' in sys.modules else False
        print("input pin", inputpin, type(inputpin))
        self.outputpin = toint(outputpin)
        if self.ispi and self.outputpin is not None:
            gpio.setup(self.outputpin, gpio.OUT, initial=0)
        self.inputpin = toint(inputpin)
        self.addrtuple = outaddr.split(':')
        if len(self.addrtuple) < 2:
            self.addrtuple = None
        else:
            #successful split, now convert 2nd element to an int
            self.addrtuple[1] = int(self.addrtuple[1])
        if self.ispi and self.inputpin is not None:
            #set up interrupt callback for pin (active-high)
            gpio.setup(self.inputpin, gpio.IN, pull_up_down=gpio.PUD_DOWN)
            gpio.add_event_detect(self.inputpin, gpio.RISING, callback=self.event, bouncetime=1000)

    def event(self, channel):
        """
        Interrupt handler callback function to handle a GPIO pin's interrupt event.
        On receipt of this event, this function will send an 'alarm' message to
        the cloud server.
        This function can be overridden safely if required.
        """
        print("rising edge detected on GPIO", channel)
        if self.addrtuple is not None:
            msg = {
                'event': 'alarm',
                'gpio': self.inputpin,
            }
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.addrtuple[0], self.addrtuple[1]))
            s.send(json.dumps(msg).encode('utf-8'))
            s.close()

    def activate(self):
        """
        Drives a GPIO pin ('outputpin' in the init args) high in response to the server command.
        This function can be overridden safely if required.
        """
        print("actuator activate")
        if self.ispi and self.outputpin:
            #set GPIO high
            gpio.output(self.outputpin, gpio.HIGH)

    def deactivate(self):
        """
        Drive a GPIO pin ('outputpin' in the init args) low in response to the server command.
        This function can be overridden safely if required.
        """
        print("actuator deactivate")
        if self.ispi and self.outputpin:
            #set GPIO low
            gpio.output(self.outputpin, gpio.LOW)

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
            self.insock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.insock.bind(('', self.inport))
            return self
        else:
            raise TypeError("cmd_listener: No input port specified, cannot use"
                " cmd_listener in 'with' statement")

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Close the socket created with __enter__() and stop any thread that has been started.
        """
        if self.insock:
            self.insock.close()
            self.insock = None

    def run(self):
        """
        Starts listening for incoming commands and routes them to the correct handler.
        """
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
        parser.add_argument('-o', '--outaddr', default=None,
            help="Output address (host:port), for sending outgoing signals."
            " MUST be a valid address, or the connection will crash.")
        parser.add_argument('-i', '--inport', default=9001,
            help="Input port, for receiving commands")

        parser.add_argument('--actuator_gpio', default=None,
            help="Output actuator GPIO (drive this GPIO when armed)")
        parser.add_argument('--event_gpio', default=None,
            help="Input event GPIO (interrupt on this GPIO going high)")
        return parser.parse_args()

    args = get_args()
    a = actuator(outputpin=args.actuator_gpio, inputpin=args.event_gpio, outaddr=args.outaddr)
    with cmd_listener(inport=args.inport, handler=a) as listener:
        listener.run()
