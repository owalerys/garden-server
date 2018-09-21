import click
import serial.tools.list_ports
from garden.db import get_db
from garden.base import Model, Collection
import PyCmdMessenger

class Garden(object):

    def __init__(self):
        self.slaves = Slave.recordsByUUID()
        self.sensors = Sensor.recordsByUUID()
        self.relays = Relay.recordsByUUID()
        self.schedules = Schedule.recordsByUUID()
        self.rules = Rule.recordsByUUID()
        self.elements = Element.recordsByUUID()
        self.consequences = Consequence.recordsByUUID()
        self.rule_limits = RuleLimit.recordsByUUID()
        self.iterator = False
        self.connection_manager = None
        self.readings = {}

    def setIterator(self):
        self.iterator = True
        if self.connection_manager is None:
            self.connection_manager = ConnectionManager()

    def isIterator(self):
        return self.iterator

    def iterate(self):
        self.setIterator()
        
        while True:
            self.tickLoop()

    def tickLoop(self):
        self.resetOfflineOnline()
        self.connection_manager.makeConnections()
        self.updateSlaves()
        self.readActiveSensors()

    def updateSlaves(self):
        online = {}

        for uuid in self.connection_manager.iterate():
            slave = self.slaves.fetchByUUID(uuid)
            online[uuid] = True
            if slave:
                if not slave.connected:
                    slave.connected = True
                    slave.save()
                    self.flagOfflineOnline()
                    click.echo("Slave marked connected in db.")
            else:
                slave = self.slaves.addNewRecord({'uuid': uuid, 'nickname': '', 'connected': True})
                slave.save()
                self.flagOfflineOnline()
                click.echo("Slave created and marked connected in db.")

        for slave in self.slaves.iterate():
            if slave.connected and slave.uuid not in online:
                slave.connected = False
                slave.save()
                self.flagOfflineOnline()
                click.echo("Slave marked disconnected in db.")

    def readActiveSensors(self):
        self.readings = {}

        for sensor in self.sensors.iterate():
            slave = self.slaves.fetchByUUID(sensor.slave_uuid)

            if sensor.active and slave.connected:
                reading = self.connection_manager.readSensor(sensor)
                self.readings[sensor.uuid] = reading

    def flagOfflineOnline(self):
        self.offline_online_flag = True

    def resetOfflineOnline(self):
        self.offline_online_flag = False

    def close(self):
        """Close out all of the connections"""
        if self.connection_manager:
            self.connection_manager.despawn()
            self.updateSlaves()

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

    def iterate(self):
        for uuid in self.connections:
            if self.isDeviceConnected(uuid):
                yield uuid

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

    def readSensor(self, sensor):
        if self.isDeviceConnected(sensor.slave_uuid):
            try:
                c = self.connections[sensor.slave_uuid]

                c.send("sensor", sensor.getPinType(), sensor.getPin(), sensor.getDriver(), sensor.getMeasurementType())
                msg = c.receive()
            except serial.serialutil.SerialException as e:
                return None

            if msg[0] == "sensor_response":
                return msg[1][1]
            else:
                return None
        else:
            return None

class Client(Model):
    _table = 'client'

class Slave(Model):
    _table = 'slave' 

class Sensor(Model):
    _table = 'sensor'

    def getPinType():
        if self.digital:
            return 'digital'
        else:
            return 'analog'

    def getPin():
        return self.pin

    def getDriver():
        return self.driver

    def getMeasurementType():
        return self.measurement_type

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
