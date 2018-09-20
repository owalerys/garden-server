import click
import serial.tools.list_ports
from garden.db import get_db
from garden.base import Model, Collection
import PyCmdMessenger

class Garden(object):

    def __init__(self):
        self.slaves = Collection(Slave).recordsByUUID()
        self.sensors = Collection(Sensor).recordsByUUID()
        self.relays = Collection(Relay).recordsByUUID()
        self.schedules = Collection(Schedule).recordsByUUID()
        self.rules = Collection(Rule).recordsByUUID()
        self.elements = Collection(Element).recordsByUUID()
        self.consequences = Collection(Consequence).recordsByUUID()
        self.rule_limits = Collection(RuleLimit).recordsByUUID()
        self.iterator = False
        self.connection_manager = None

    def setIterator(self):
        self.iterator = True
        if self.connection_manager is None:
            self.connection_manager = ConnectionManager()

    def isIterator(self):
        return self.iterator

    def iterate(self):
        self.setIterator()
        
        while True:
            self.connection_manager.makeConnections()

    def close(self):
        """Close out all of the connections"""
        if self.connection_manager:
            self.connection_manager.despawn()

class ConnectionManager(object):

    _commands = [["error", "s"],
            ["uuid", ""],
            ["uuid_response", "s"],
            ["sensor", "siss"],
            ["sensor_response", "if"],
            ["relay", "i"],
            ["relay_response", "ii"],
            ["disabled_output", "ii"]]
    
    def __init__(self):
        self.connections = {}
        self.connections_port_to_uuid = {}

    def makeConnections(self):
        ports_to_check = serial.tools.list_ports.grep("\/dev\/ttyACM[0-9]+")

        for port in ports_to_check:

            device = port.device
            if device in self.connections_port_to_uuid:
                uuid = self.connections_port_to_uuid[device]
            else:
                uuid = None

            if not self.isPortAssigned(device):
                self.establishConnection(device)
                continue
            
            if not self.isDeviceConnected(uuid):
                self.terminateConnection(device)
                continue

            if not self.doesUuidMatch(uuid):
                self.terminateConnection(device)
                self.establishConnection(device)
                continue

    def despawn(self):
        click.echo("Shutting down all connections")
        for device in self.connections_port_to_uuid:
            self.terminateConnection(device)

    def establishConnection(self, device):
        click.echo("Attempting to establish connection on %s" % device)
        
        try:
            arduino = PyCmdMessenger.ArduinoBoard(device, baud_rate=115200)
            c = PyCmdMessenger.CmdMessenger(arduino, self._commands)
        except serial.serialutil.SerialException as e:
            c = None

        if c and c.board.comm.is_open:
            
            try:
                c.send("uuid")
                msg = c.receive()
            except serial.serialutil.SerialException as e:
                click.echo("Fatal SerialException on connection")
                return

            if msg[0] == "uuid_response":
                uuid = msg[1][0]

                self.connections_port_to_uuid[device] = uuid
                self.connections[uuid] = c
                click.echo("Succeeded for %s" % uuid)
            else:
                c.board.close()
                click.echo("Failed 2 with %s" % msg[1])
        else:
            click.echo("Failed 1")

    def terminateConnection(self, device):
        if device in self.connections_port_to_uuid:
            uuid = self.connections_port_to_uuid[device]
        else:
            uuid = None

        click.echo("Closing connection on %s" % device)

        if not uuid:
            click.echo("No uuid relation found")
            return

        click.echo("Board: %s" % uuid)

        if uuid in self.connections:
            c = self.connections[uuid]
        else:
            c = None

        if not c:
            self.connections_port_to_uuid[device] = None
            click.echo("No connection instance found")
            return

        if not c.board.comm.is_open:
            self.connections_port_to_uuid[device] = None
            self.connections[uuid] = None
            click.echo("Connection no longer open")
            return

        try:
            c.board.close()
        except serial.serialutil.SerialException as e:
            click.echo("Failure to fully close, dumping connection anyway.")

        self.connections_port_to_uuid[device] = None
        self.connections[uuid] = None
        click.echo("Successfully closed.")

    def isPortAssigned(self, device):
        if device in self.connections_port_to_uuid and self.connections_port_to_uuid[device]:
            return True
        else:
            return False

    def isDeviceConnected(self, uuid):
        if uuid in self.connections and self.connections[uuid]:
            return self.connections[uuid].board.comm.is_open
        else:
            return False
    
    def doesUuidMatch(self, uuid):
        c = self.connections[uuid]
        
        try:
            c.send("uuid")
            msg = c.receive()
        except serial.serialutil.SerialException as e:
            return False;

        if msg[0] == "uuid_response":
            return msg[1][0] == uuid
        else:
            return False

class Client(Model):
    _table = 'client'

class Slave(Model):
    _table = 'slave' 

class Sensor(Model):
    _table = 'sensor'

class Relay(Model):
    _table = 'relay'

class Schedule(Model):
    _table = 'schedule'

class Rule(Model):
    _table = 'rule'

class Element(Model):
    _table = 'element'

class Consequence(Model):
    _table = 'consequence'

class RuleLimit(Model):
    _table = 'rule_limit'

class Activation(Model):
    _table = 'activation'

class Measurement(Model):
    _table = 'measurement'
