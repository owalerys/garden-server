import click
import serial.tools.list_ports
from garden.db import get_db
from garden.base import Model, Collection
import PyCmdMessenger
import datetime
import time

class Garden(object):

    def __init__(self):
        self.initializeRecords()

        self.iterator = False
        self.connection_manager = None
        self.readings = {}
        self.scheduler = {}
        self.relay_signals = {}
        self.relay_results = {}

    def initializeRecords(self):
        self.slaves = Slave.recordsByUUID()
        self.sensors = Sensor.recordsByUUID()
        self.relays = Relay.recordsByUUID()
        self.schedules = Schedule.recordsByUUID()
        self.rules = Rule.recordsByUUID()
        self.elements = Element.recordsByUUID()
        self.consequences = Consequence.recordsByUUID()
        self.rule_limits = RuleLimit.recordsByUUID()

        for rule in self.rules.iterate():
            rule.setChildParams(
                    self.elements.filteredCollection('rule_uuid', rule.uuid),
                    self.consequences.filteredCollection('rule_uuid', rule.uuid),
                    self.rule_limits.filteredCollection('rule_uuid', rule.uuid))
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
        self.checkSchedule()
        self.calculateForcedRelays()
        self.checkRules()
        self.contactRelays()

    def updateSlaves(self):
        online = {}

        for uuid in self.connection_manager.iterate():
            slave = self.slaves.fetchByUUID(uuid)
            online[uuid] = True
            if slave:
                if not slave.connected:
                    slave.set('connected', True)
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
                slave.set('connected', False)
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

    def checkSchedule(self):
        self.scheduler = {}

        for schedule in self.schedules.iterate():
            if schedule.active and schedule.appliesNow():
                self.scheduler[schedule.uuid] = True
            else:
                self.scheduler[schedule.uuid] = False

    def calculateForcedRelays(self):
        self.relay_signals = {}

        for relay in self.relays.iterate():
            slave = self.slaves.fetchByUUID(relay.slave_uuid)

            if relay.active and slave.connected:
                if relay.manual:
                    self.relay_signals[relay.uuid] = True
                    relay.setForce()
                else:
                    self.relay_signals[relay.uuid] = False
                    relay.cancelForce()

    def checkRules(self):
        for rule in self.rules.iterate():
            if rule.evaluate(self.readings, self.scheduler):
                for consequence in rule.iterateConsequences():
                    relay = self.relays.fetchByUUID(consequence.relay_uuid)
                    
                    if relay and relay.active:
                        self.relay_signals[relay.uuid] = True

    def contactRelays(self):
        self.relay_results = {}

        for relay in self.relays.iterate():
            if relay.active:
                if relay.isForced():
                    self.relay_results[relay.uuid] = self.connection_manager.setRelay(relay)
                else:
                    if relay.uuid in self.relay_signals and (self.relay_signals[relay.uuid] == True or self.relay_signals[relay.uuid] == False):
                        signal = self.relay_signals[relay.uuid]
                        allowed = relay.setTo(signal)

                        self.relay_results[relay.uuid] = self.connection_manager.setRelay(relay)
                    else:
                        self.relay_results[relay.uuid] = None

    def flagOfflineOnline(self):
        self.offline_online_flag = True

    def resetOfflineOnline(self):
        self.offline_online_flag = False

    def close(self):
        """Close out all of the connections"""
        if self.connection_manager:
            self.connection_manager.despawn()
        self.updateSlaves()

        for relay in self.relays.iterate():
            relay.endActivation()

        for rule in self.rules.iterate():
            rule.endActivation()

class ConnectionManager(object):

    _commands = [["error", "s"],
            ["uuid", ""],
            ["uuid_response", "s"],
            ["sensor", "siss"],
            ["sensor_response", "if"],
            ["relay", "ii"],
            ["relay_response", "ii"]]
    
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

                if len(uuid) != 36:
                    c.board.close()
                    click.echo("Invalid uuid length received for %s" % uuid)
                    return

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

                click.echo("Reading for: %s, %s, %s, %s, %s" % (sensor.uuid, sensor.getPinType(), sensor.getPin(), sensor.getDriver(), sensor.getMeasurementType()))

                c.send("sensor", sensor.getPinType(), sensor.getPin(), sensor.getDriver(), sensor.getMeasurementType())
                msg = c.receive()
            except serial.serialutil.SerialException as e:
                click.echo("Reading exception on: %s" % sensor.uuid)
                return None

            if msg[0] == "sensor_response":
                click.echo("Recorded output: %s, %s" % (msg[1][0], msg[1][1]))
                return msg[1][1]
            else:
                click.echo("Error details: %s" % msg[1][0])
                return None
        else:
            return None

    def setRelay(self, relay):
        if self.isDeviceConnected(relay.slave_uuid):
            try:
                c = self.connections[relay.slave_uuid]

                c.send("relay", relay.getPin(), relay.getCurrentState())
                msg = c.receive()
            except serial.serialutil.SerialException as e:
                return None

            if msg[0] == "relay_response":
                relay.recordCurrentState(msg[1][1])
                return msg[1][1]
            else:
                return None
        else:
            return None

class Client(Model):
    _table = 'client'

class Slave(Model):
    _table = 'slave' 

    def preSave(self):
        self.setAttribute('last_seen', datetime.datetime.now())

class Sensor(Model):
    _table = 'sensor'

    def getPinType(self):
        if self.digital:
            return 'digital'
        else:
            return 'analog'

    def getPin(self):
        return self.pin

    def getDriver(self):
        return self.driver

    def getMeasurementType(self):
        return self.measurement_type

class Relay(Model):
    _table = 'relay'
    _safety_seconds = 10

    def afterInit(self):
        self.current_state = False
        self.forced = False
        self.last_toggle = 0

        db = get_db()
        rows = db.execute('SELECT * FROM activation WHERE relay_uuid = ? AND end_time IS NULL', (self.uuid,)).fetchall()
        activations = Collection(Activation)
        activations.pushRows(rows)

        for activation in activations.iterate():
            activation.terminate()

        self.current_activation = None

    def setForce(self):
        self.current_state = True
        self.forced = True
        self.last_toggle = 0

        if self.current_activation is None:
            self.current_activation = Activation({'relay_uuid': self.uuid, 'start_time': datetime.datetime.now(), 'end_time': None, 'last_update': datetime.datetime.now()})
            self.current_activation.save()

    def cancelForce(self):
        self.forced = False

        if self.current_activation and self.current_activation.getAttribute('end_time') is None:
            self.current_activation.terminate(datetime.datetime.now())
            self.current_activation.save()
            self.current_activation = None

    def endActivation(self):
        self.cancelForce()

    def isForced(self):
        return self.forced

    def setTo(self, new_state):
        current_utc = time.time()

        if new_state != self.current_state:
            can = current_utc >= (self.last_toggle + self._safety_seconds)

            if can:
                self.current_state = new_state
                self.last_toggle = current_utc
                return True
            else:
                return False
        else:
            return True

    def getPin(self):
        return self.pin

    def getCurrentState(self):
        if self.current_state == True:
            return 1
        else:
            return 0

    def recordCurrentState(self, state):
        if state:
            self.current_state = True
        else:
            self.current_state = False

class Schedule(Model):
    _table = 'schedule'

    def appliesNow(self):

        now = datetime.datetime.now()
        current = now.hour * 3600 + now.minute * 60 + now.second

        if self.schedule_end < self.schedule_start:
            return current >= self.schedule_start or current < self.schedule_end
        else:
            return current >= self.schedule_start and current < self.schedule_end

class Rule(Model):
    _table = 'rule'

    def afterInit(self):
        self.element_track = {}

    def setChildParams(self, elements, consequences, limits):
        self.elements = elements
        self.consequences = consequences
        self.limits = limits

        for element in self.elements.iterate():
            if element.uuid not in self.element_track:
                self.element_track[element.uuid] = None

        back_in_time = datetime.datetime.now() - datetime.timedelta(hours = 24)

        db = get_db()
        records = db.execute('SELECT * FROM activation WHERE rule_uuid = ? AND (end_time IS NULL OR end_time >= ?)', (self.uuid, back_in_time.isoformat())).fetchall()

        self.activations = Collection(Activation)
        self.activations.pushRows(records)

        for activation in self.activations.iterate():
            activation.terminate()

        self.current_activation = None

    def endActivation(self):
        if self.current_activation is not None and self.current_activation.getAttribute('end_time') is None:
            self.current_activation.setAttribute('end_time', datetime.datetime.now())
            self.current_activation.save()
            self.current_activation = None

    def startActivation(self):
        if self.current_activation is None:
            self.current_activation = Activation({'rule_uuid': self.uuid, 'start_time': datetime.datetime.now(), 'end_time': None, 'last_update': datetime.datetime.now()})
            self.current_activation.save()
            self.activations.pushExistingModel(self.current_activation)

    def evaluate(self, readings, scheduler):
        can_evaluate = True if self.schedule_uuid in scheduler and scheduler[self.schedule_uuid] == True else False

        if not can_evaluate:
            self.updateActivation(False)
            return False

        self.checkReadings(readings)
        elements_passed = self.elementsPass()
        limits_passed = self.limitsPass()

        if elements_passed and limits_passed:
            self.updateActivation(True)
            return True
        else:
            self.updateActivation(False)
            return False

    def checkReadings(self, readings):
        for element in self.elements.iterate():
            if element.sensor_uuid in readings and readings[element.sensor_uuid] is not None:
                reading = readings[element.sensor_uuid]
                max_value = element.max_value
                min_value = element.min_value
                target_value = element.target_value
                uuid = element.uuid

                in_target = False
                triggered = False

                if element.max_value is not None:
                    in_target = reading <= max_value and reading >= target_value
                    triggered = reading >= max_value
                elif element.min_value is not None:
                    in_target = reading >= min_value and reading <= target_value
                    triggered = reading <= min_value
                else:
                    self.element_track[uuid] = None
                    continue

                current_track = self.element_track[uuid]

                if current_track == 1:
                    self.element_track[uuid] = 1 if in_target else 0
                elif current_track == 0:
                    self.element_track[uuid] = 1 if triggered else 0
                elif current_track is None:
                    self.element_track[uuid] = 1 if triggered else 0
                else:
                    self.element_track[uuid] = None
            else:
                self.element_track[element.uuid] = None
                continue

    def elementsPass(self):
        if self.elements.count() == 0:
            return True

        if self.logic_type == 'or':
            track = 0
        elif self.logic_type == 'and':
            track = 1
        else:
            return False

        for element in self.elements.iterate():
            if self.element_track[element.uuid] is None:
                return False
            elif self.element_track[element.uuid] == 1:
                if self.logic_type == 'and':
                    track = 1 if track == 1 else 0
                else:
                    track = 1
            elif self.element_track[element.uuid] == 0:
                if self.logic_type == 'and':
                    track = 0

        return True if track == 1 else False

    def limitsPass(self):
        for limit in self.limits.iterate():
            if limit.exceeded(self.activations):
                return False

        return True

    def updateActivation(self, isActive):
        if isActive == True:
            self.startActivation()
        else:
            self.endActivation()

    def iterateConsequences(self):
        return self.consequences.iterate()

class Element(Model):
    _table = 'element'

class Consequence(Model):
    _table = 'consequence'

class RuleLimit(Model):
    _table = 'rule_limit'

    def exceeded(self, activations):
        every = self.every
        period = self.period
        count = 0

        start = (datetime.datetime.now() - datetime.timedelta(seconds = every)).timestamp()
        end = datetime.datetime.now().timestamp()

        for activation in activations.iterate():
            activation_start = activation.start_time.timestamp()
            activation_end = (activation.end_time if activation.end_time is not None else datetime.datetime.now()).timestamp()

            starting_value = max(start, activation_start)
            ending_value = min(end, activation_end)

            if ending_value > starting_value:
                count += (ending_value - starting_value)

        return not (count < period)

class Activation(Model):
    _table = 'activation'

    def preSave(self):
        self.setAttribute('last_update', datetime.datetime.now())

    def terminate(self, timestamp = None):
        if timestamp is not None:
            self.setAttribute('end_time', timestamp)
        else:
            self.setAttribute('end_time', self.getAttribute('last_update'))
        self.save()

class Measurement(Model):
    _table = 'measurement'
