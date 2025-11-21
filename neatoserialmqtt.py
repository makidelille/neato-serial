
"""MQTT interface for Neato Serial."""
from config import settings
import json
import time
import sys
import paho.mqtt.client as mqtt
from neatoserial import NeatoSerial
import logging

ns = NeatoSerial()
serial_number = ns.getSerialNumber()

prefix = 'vacuum/neato_' + serial_number

#Function utilized when MQTT Autodiscovery is used - uses "state" schema in Homeassistant
def discovery_payload():
    software_version = ns.getSoftwareVersion()
    is_docked = ns.getExtPwrPresent()
    is_cleaning = ns.getCleaning()
    is_charging = ns.getChargingActive()
    fan_speed = ns.getVacuumRPM()
    battery_level = ns.getBatteryLevel()
    error = ns.getError()

    config_data = {
        'command_topic': prefix + '/command',
        'device': {
            'identifiers': ['neato_' + serial_number],
            'name': settings['device']['name'],
            'manufacturer': 'Neato Robotics',
            'model': settings['device']['model'],
            'sw_version': software_version
        },
        'name': settings['device']['name'],
        'unique_id': 'neato_' + serial_number,
        'payload_clean_spot': 'Clean Spot',
        'payload_locate': 'PlaySound 19',
        'payload_start': 'Clean',
        'payload_stop': 'Clean Stop',
        'schema': 'state',
        'state_topic': prefix + '/state',
        'supported_features': ['start', 'stop',  'status', 'locate', 'clean_spot']
    }

    sensor_config_data = {
        'device': {
            'identifiers': ['neato_' + serial_number],
            'name': settings['device']['name'],
        },
        'device_class': 'battery',
        'name': settings['device']['name'],
        'unique_id': 'neato_' + serial_number + '_battery_level',
        'state_class': 'measurement',
        'state_topic': prefix + '/battery',
        'unit_of_measurement': '%',
        'value_template': '{{ value_json.battery_level }}',
        'json_attributes_template': "{{ value_json | tojson }}"
    }

    state_data = {}
    battery_data = {}
    battery_data["battery_level"] = battery_level
    state_data["fan_speed"] = fan_speed
    state_data["charging"] = is_charging
    if is_docked:
        state_data["state"] = "docked"
    elif is_cleaning:
        state_data["state"] = "cleaning"
    elif error:
        log.debug("Error from Neato: "+str(error[1]))
        state_data["error"] = error[1]
        state_data["state"] = "error"
    else:
        state_data["state"] = "idle"

    #Convert config, state, and attributes payloads to json + publish them
    json_config_data = json.dumps(config_data)
    json_sensor_config = json.dumps(sensor_config_data)
    json_state_data = json.dumps(state_data)
    json_battery_data = json.dumps(battery_data)
    log.debug("Sending MQTT Config Message: "+str(json_config_data))
    client.publish(settings['mqtt']['discovery_topic'] + '/vacuum/neato_' + serial_number + '/config', json_config_data)
    log.debug("Sending MQTT Config Message: "+str(json_sensor_config))
    client.publish(settings['mqtt']['discovery_topic'] + '/sensor/neato_' + serial_number + '/config', json_sensor_config)
    log.debug("Sending vacuum state message: "+str(json_state_data))
    client.publish(prefix + '/state', json_state_data)
    log.debug("Sending vacuum battery message: "+str(json_battery_data))
    client.publish(prefix + '/battery', json_battery_data)
    time.sleep(settings['mqtt']['publish_wait_seconds'])

#Function utilized when manual MQTT configuration is used - uses "legacy" schema in Homeassistant
def legacy_payload():
    legacy_data = {}
    legacy_data["docked"] = is_docked
    legacy_data["cleaning"] = is_cleaning
    legacy_data["charging"] = is_charging
    legacy_data["fan_speed"] = fan_speed
    error = ns.getError()
    if error:
        log.debug("Error from Neato: "+str(error))
        legacy_data["error"] = error[1]
    json_legacy_data = json.dumps(legacy_data)
    log.debug("Sending vacuum state message: "+str(json_legacy_data))
    client.publish(settings['mqtt']['state_topic'], json_legacy_data)
    battery_data = {}
    battery_data["battery_level"] = battery_level
    json_battery_data = json.dumps(battery_data)
    log.debug("Sending vacuum battery message: "+str(json_battery_data))
    client.publish(settings['mqtt']['battery_topic'], json_battery_data)
    time.sleep(settings['mqtt']['publish_wait_seconds'])

def on_message(client, userdata, msg):
    """Message received."""
    inp = msg.payload.decode('ascii')
    log.info("Message received: "+inp)
    if 'discovery_topic' in settings['mqtt']:
            feedback = ns.write(inp)
            log.info("Feedback from device: "+feedback)
    else:
        if (inp == "Clean") or (inp == "Clean Spot"):
            on_message_data={}
            on_message_data["docked"] = is_docked
            on_message_data["cleaning"] = True
            on_message_data["charging"] = is_charging
            on_message_data["fan_speed"] = fan_speed
            json_on_message_data = json.dumps(on_message_data)
            #Use secondary client connection to set state to cleaning before Pi reboots (Can't publish with primary client whithin callback function)
            feedback = ns.write(inp)
            log.info("Feedback from device: "+feedback)
        elif inp == "Clean Stop":
            on_message_data={}
            on_message_data["docked"] = is_docked
            on_message_data["cleaning"] = False
            on_message_data["charging"] = is_charging
            on_message_data["fan_speed"] = fan_speed
            json_on_message_data = json.dumps(on_message_data)
            #Use secondary client connection to set state to cleaning before Pi reboots (Can't publish with primary client whithin callback function)
            feedback = ns.write(inp)
            log.info("Feedback from device: "+feedback)
        else:
            feedback = ns.write(inp)
            log.info("Feedback from device: "+feedback)

def on_connect(client, userdata, flags, rc):
    """Broker responded to connection request"""
    if rc == 0:
        log.info("Connection to broker successful")
    else:
        log.info("Problem connecting to broker")

def on_disconnect(client, userdata, rc):
    """Handle MQTT client disconnect."""
    #Set availability to offline if disconnected from MQTT Broker
    client.loop_stop(force=False)
    if rc != 0:
        log.info("Unexpected disconnection.")
    else:
        log.info("Disconnected.")


#logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
log.addHandler(ch)
fh = logging.FileHandler('neatoserial.log')
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
log.addHandler(fh)

log.debug("Starting")
#Primary Client
client = mqtt.Client()
client.on_message = on_message
client.on_disconnect = on_disconnect
client.on_connect = on_connect
client.username_pw_set(settings['mqtt']['username'],
                       settings['mqtt']['password'])
log.debug("Connecting")
client.connect(settings['mqtt']['host'], settings['mqtt']['port'])
client.subscribe(prefix + '/command', qos=1)
log.debug("Setting up serial")


log.debug("Ready")
client.loop_start()
while True:
    # try:
    #if not ns.getIsConnected():
    #    ns.reconnect()
    serial_number = ns.getSerialNumber()
    software_version = ns.getSoftwareVersion()
    is_docked = ns.getExtPwrPresent()
    is_cleaning = ns.getCleaning()
    is_charging = ns.getChargingActive()
    fan_speed = ns.getVacuumRPM()
    battery_level = ns.getBatteryLevel()
    error = ns.getError()
    #Determine whether end-user is using MQTT Autodiscovery or Manual configuration
    if 'discovery_topic' in settings['mqtt']:
        discovery_payload()
    else:
        legacy_payload()
        # except Exception as ex:
        #     log.error("Error getting status: "+str(ex))
