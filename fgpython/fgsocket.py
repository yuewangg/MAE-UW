#! /usr/bin/python
""" Send commands between Python and JSBSim over TCP.

Author: Linnea Persson, laperss@kth.se 

Suitable for sending many commands in a stream.
It is mainly used to update the reference values for the vehicles. 
You must set the heading with which you define the heading relative to.

Usage:
    FGSocketConnection.heading = HEADING
    uav_socket = FGSocketConnection(5515, 5514)
    ugv_socket = FGSocketConnection(5526, 5525)
Set the reference values to send:
    uav_socket.update_setpoint('acceleration', 0.3)
    ugv_socket.update_setpoint('heading', 12.0)
Set the bias/scale values:
    uav_socket.update_scale('acceleration', 3.28084)
    ugv_socket.update_bias('heading', 120.0)
"""
from __future__ import print_function
import math
import _thread
import socket
import re
import xml.etree.ElementTree as ET
import os

RAD2DEG = 57.2957795
DEG2RAD = 0.0174532925
FEET2M = 0.3048
M2FEET = 3.28084


class CommunicationSetup(object):
    """ Communication definition struct """

    def __init__(self, input_protocol, output_protocol, input_port, output_port):
        self.in_protocol = input_protocol
        self.out_protocol = output_protocol
        self.input_port = input_port
        self.output_port = output_port


class FGSocketConnection(object):
    """ JSBSim communication system. 
        Uses UDP to reieve data from and send data to FlightGear.

        The protocols for receiving data are defined in:
            * flightgear/protocols/UAVProtocol.xml
            * flightgear/protocols/UAVProtocol.xml
        The protocol for sending data is: 
            * flightgear/protocols/InputProtocol.xml
    """
    heading = 0.0

    def __init__(self, comm_setup):
        self.data = []

        self.output_port = comm_setup.output_port
        self.input_port = comm_setup.input_port
        self.input_protocol = comm_setup.in_protocol
        self.output_protocol = comm_setup.out_protocol
        self.update = False
        self.connected = False

        path = os.path.dirname(os.path.abspath(__file__))
        output_script = os.path.join(
            path, '../flightgear/protocols/'+self.output_protocol+'.xml')
        input_script = os.path.join(
            path, '../flightgear/protocols/'+self.input_protocol+'.xml')
        input_root = ET.parse(input_script).getroot()
        self.sp = []
        self.scale = []
        self.bias = []
        self.id = dict()
        itr = 0
        for chunk in input_root[0][0].findall('chunk'):
            name = chunk.find('name').text
            self.sp.append(0.0)
            self.scale.append(1.0)
            self.bias.append(0.0)
            self.id[name] = itr
            itr += 1

        self.setup_sockets()

    def has_variable(self, prop):
        return prop in self.id.keys()

    def update_bias(self, prop, bias):
        self.bias[self.id[prop]] = bias

    def update_scale(self, prop, scale):
        self.scale[self.id[prop]] = scale

    def update_setpoint(self, prop, value):
        self.sp[self.id[prop]] = value

    def get_setpoint(self, prop):
        return self.sp[self.id[prop]]

    def setup_sockets(self):
        """ Setup the socket communication """
        self.socket_in = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket_out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.socket_in.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_out.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.socket_in.bind(('localhost', self.input_port))

    def send_command_udp(self, command, port):
        """ Send actuator commands to JSBSim/FlightGear via UDP. """
        message = ''
        for cmd in command[:-1]:
            message = '%s%f, ' % (message, cmd)
        message = '%s%s\n' % (message, str(command[-1]))
        self.socket_out.sendto(message.encode(), ('localhost', port))

    def start_receive_state(self):
        """ Starts the thread for reading data from flightGear """
        self.update = True
        _thread.start_new_thread(self.receive_state, ())

    def receive_state(self):
        """ Separates data and updates the "data" variable"""
        if not self.connected:
            data, addr = self.socket_in.recvfrom(2048)  # Wait for initial data
            self.connected = True

        while self.update == True:
            data, addr = self.socket_in.recvfrom(2048)
            data = data.decode()
            data.rstrip('\n')
            if not data:
                break
            self.data = [float(i) for i in re.split(r'\t+', data)]

    def get_state(self, idx):
        """ Return the current vehicle state """
        return [self.data[i] for i in idx]

    def send_cmd(self):
        """ Define the message and send to UDP function. """
        command = [self.scale[i]*(self.sp[i] + self.bias[i])
                   for i in range(len(self.sp))]
        self.send_command_udp(command, self.output_port)
