import datetime
import json

import arrow

# see README for details ("How it works")

# NAMING CONVENTIONS
# device: the hardware part. It has a name (visible in "Devices" in HA), a model etc.
# channel: the way actual plugs are addressed in a device (see description in the README for details)
# entity: a combination of a device and one of its channels (visible in "Entities" in HA). The actual "switch"

# status of all devices, it is updated as the events happen and holds a state view of everything
devices = {}
try:
    for device in pyscript.config['meross']:
        # list of channels for this device
        channels = range(device['channels']) if device['channels'] == 1 else range(1, device['channels'])
        devices[device['id']] = {
            "channel": {},
            "device": {
                "id": device['id'],
                "channels": list(channels),
                "name": device['name'],
                "online": 'online',     # the optimistic approach, will be proven wrong by a function below (not setting the timestamp)
            }
        }
        log.debug(f"added device with id {device['id']}: {devices[device['id']]}")
except KeyError as e:
    raise Exception(f"missing parameters in configuration.yaml: {e}")
else:
    log.debug("buildup of devices state manager complete")

@service
@time_trigger("startup")
def create_new_devices_and_entities_in_HA():
    """
    creation of all MQTT devices in HA from the configuration
    it is an idempotent operation and does not modify the manual renames done via the UI
    """
    for device_id in devices.keys():
        log.debug(f"configuring device {device_id}")
        for channel in devices[device_id]['device']['channels']:
            # payload is described at https://www.home-assistant.io/integrations/switch.mqtt/
            name = devices[device_id]['device']['name']
            payload = {
                "platform": "mqtt",
                "unique_id": f"{device_id}_{channel}",
                "name": f"{name}_{channel}",
                "state_topic": f"meross/{device_id}/{channel}/state",
                "command_topic": f"meross/{device_id}/{channel}/set",
                "availability_topic": f"meross/{device_id}/{channel}/available",
                "payload_on": "ON",
                "payload_off": "OFF",
                "optimistic": False,
                "qos": 0,
                "retain": True,
                "device": {
                    "identifiers": device_id,
                    "manufacturer": "Meross",
                    "model": name,  # set to the first name when the device is created, will not change upon rename of the device in the UI and allow for a mapping to the name that is in the configuration
                    "name": name,
                }
            }
            # topic is described at https://www.home-assistant.io/docs/mqtt/discovery/
            topic = f"homeassistant/switch/meross/{name}_{channel}/config"
            mqtt.publish(
                topic=topic,
                payload=json.dumps(payload),
                retain=True
            )
            log.info(f"sent autodiscovery for {topic} with payload {payload}")


@mqtt_trigger('/appliance/+/publish')
def set_state_in_HA_when_device_speaks(**data):
    """
    When a device does something, it publishes the results of this something to /appliance/<id>/publish
    This function handles these messages to update the state of the relevant entity in HA,
    as well as its online state (as a nice to have because this is handled independently as well)
    It is somehow the twin of send_order_to_device_when_state_is_changed_in_HA(), the other way round
    """
    device_id = data['topic'].split('/')[2]
    if device_id not in devices.keys():
        log.warning(f"device {device_id} is broadcasting, but it is not defined in configuration.yaml")
        return
    payload = json.loads(data['payload'])
    log.debug(f"received message on /appliance/{device_id}/publish: {data['payload']}")
    # we are for now interested only by events triggered by a toggle of a plug
    if payload['header']['namespace'] == "Appliance.Control.ToggleX":
        # is this a single entry (= a single plug, sends a list), or a set of entries (= a power strip that sends
        # a dict with more info, even when one plug is toggled)?
        # we need consistency → everything is a list to iterate on afterwards
        if type(payload['payload']['togglex']) == dict:
            payload['payload']['togglex'] = [payload['payload']['togglex']]
        for entry in payload['payload']['togglex']:
            channel = entry['channel']
            state = 'ON' if entry['onoff'] == 1 else 'OFF'
            # publish the state of the entity
            mqtt.publish(
                topic=f"meross/{device_id}/{channel}/state",
                payload=state,
                retain=True
            )
            # publish that the entity is online
            mqtt.publish(
                topic=f"meross/{device_id}/{channel}/available",
                payload='online',
                retain=True
            )
            log.info(f"device {devices[device_id]['device']['name']}, channel {channel} → {state}")


@mqtt_trigger('meross/+/+/set')
def send_order_to_device_when_state_is_changed_in_HA(**data):
    """
    When changing in HA the state of an entity, a message is sent to meross/<device>/<channle>/set
    This function handles this message to send to the real device the actual payload to make it toggle the power
    It is somehow the twin of set_state_in_HA_when_device_speaks(), the other way round
    """
    device_id = data['topic'].split('/')[1]
    channel = data['topic'].split('/')[2]
    payload = data['payload']
    mqtt.publish(
        topic=f"/appliance/{device_id}/subscribe",
        payload=json.dumps({
            "header": {
                "messageId": "2153717a8d291373a177b59108dbb2a3",    # see README for details ("How it works")
                "namespace": "Appliance.Control.ToggleX",
                "method": "SET",
                "payloadVersion": 1,
                "from": f"meross/{device_id}/{channel}/ack",
                "timestamp": 1609405973,     # see README for details ("How it works")
                "timestampMs": 980,      # see README for details ("How it works")
                "sign": "fd3d14744e3d07dfcfa0e3991d9ee3dc"   # see README for details ("How it works")
            },
            "payload": {
                "togglex": {
                    "channel": int(channel),
                    "onoff": 0 if payload == 'OFF' else 1
                }
            }
        })
    )
    log.debug(f"order sent to device {devices[device_id]['device']['name']}, channel {channel} → {payload}")



@service
@time_trigger(f"period({datetime.datetime.now()}, 1m)")
def send_request_for_status_to_all_configured_devices():
    """
    In order to check if a device is online, this function sends on a regular basis to all devices configured in configuration.yaml
    a request to send back a status of its system. These messages are monitored by handle_system_state_messages_that_were_requested_and_set_online_status()
    """
    for device in pyscript.config['meross']:
        device_id = device['id']
        mqtt.publish(
            topic=f"/appliance/{device_id}/subscribe",
            payload=json.dumps({
                "header": {
                    "messageId": "2153717a8d291373a177b59108dbb2a3",
                    "namespace": "Appliance.System.All",
                    "method": "GET",
                    "payloadVersion": 1,
                    "from": f"/appliance/{device_id}/system",
                    "timestamp": 1609405973,
                    "timestampMs": 980,
                    "sign": "fd3d14744e3d07dfcfa0e3991d9ee3dc"
                },
                "payload": {}
            })
        )
    log.debug("sent status request to all configured devices")


# monitor answers to requests for status
@mqtt_trigger('/appliance/+/system')
def handle_system_state_messages_that_were_requested_and_set_online_status(**data):
    """
    Following a request for status, the devices that are online will reply.
    This function monitors these messages to update the online status of the devices that reacted
    """
    device_id = data['topic'].split('/')[2]
    # check if device is already online, according to the state we keep
    if devices[device_id]['device']['online'] == 'online':
        log.debug(f"device {device_id} is already online")
        devices[device_id]['device']['when'] = arrow.now().isoformat()
    else:
        log.info(f"device {device_id} is back online ♥")
        # update device status in our state manager (devices)
        devices[device_id]['device']['online'] = 'online'
        devices[device_id]['device']['when'] = arrow.now().isoformat()
        # update online status of the entities (channels)
        for channel in devices[device_id]['device']['channels']:
            mqtt.publish(
                topic=f"meross/{device_id}/{channel}/available",
                payload="online",
                retain=True
            )


@time_trigger(f"period({datetime.datetime.now()}, 1m)")
def check_if_a_device_is_offline(**data):
    """
    A device that does not respond to send_request_for_status_to_all_configured_devices() for some time
    is offline.
    This function checks its "staleness" and updates its online ststus if appropriate
    """
    for device_id in devices.keys():
        when = devices[device_id]['device'].get('when')
        if not when:
            # there is no timestamp, means that the state machine was just created. We are optimistic and pass for now but we set the timestamp
            devices[device_id]['device']['when'] = arrow.now().isoformat()
            log.debug(f"optimistic online for {device_id}, will see on next round")
            continue
        if arrow.get(when) < arrow.now().shift(minutes=-2): # should be synchronized with how often we poll for status (1 minute)
            if devices[device_id]['device']['online'] == 'online':
                log.warning(f"device {device_id} is now offline ಠ‸ಠ, last online was on {when} ")
            for channel in devices[device_id]['device']['channels']:
                mqtt.publish(
                    topic=f"meross/{device_id}/{channel}/available",
                    payload="offline",
                    retain=True
                )
                devices[device_id]['device']['online'] = 'offline'
        else:
            log.debug(f"device {device_id} is online (responding to status request)")
