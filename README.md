# Local MQTT management of MEROSS devices

**WARNING:** This work in based on an afternoon of coding and experimenting to move my Meross devices from the company cloud to my own MQTT server.

It works in production (that is in my house) for some time already.

~~The code is not well documented yet, but I want to improve that.~~ (done)
It will also change frequently when I comment it, make some modifications, etc. but I do not expect major breaking changes because I already use it in "production", and my family tolerance to the lack of lights is limited. (update: no major chnages should be expected now, just improvements)

## Prerequisites
- `pyscript` (https://github.com/custom-components/pyscript) installed in Home Assistant: it is the heart of the solution, handling the MQTT messges back and forth
- MQTT configured in Home Assistant (https://www.home-assistant.io/integrations/mqtt/). The [autodiscovery](https://www.home-assistant.io/docs/mqtt/discovery/) must be enabled.
- your MEROSS device must be connected to your local MQTT broker, not to the company cloud. How to do it is explained [here](https://github.com/bytespider/Meross/wiki/MQTT). 
- you must know the unique ID of the Meross device. You retrieve it when connecting your device via @bytespider's utility, it will be similar to `2005280221783980814148e1e91d7af1`.
- (optional) some understanding of Python is useful as nothing is click-n-go for now
- (optional) `git` if you want to update the code as it changes more easily

## Installation

The main directory of Home Assistant (the one you find `configuration.yaml` in) is referred to as `<config>` in the instuctions below.

Update your `configuration.yaml` file under the `pyscript` section. An example is (see exmplanation below):

```
pyscript:
  allow_all_imports: true
  hass_is_global: true
  meross:
    - name: meross01
      id: 2005280221783980814148e1e91d7af1
      channels: 1
      model: mss110
    - name: meross02
      id: 2004280221733980814148e1f91d7af1
      channels: 6
      model: mss425f
```

Meross devices feature a concept called "channel". A channel is a way to contact a specific plug in a strip. The channel `0` is the "main channel" - the one that controls the main "on/off" button on a plug or a power strip.

For a single plug, this channel obviously is the only one available as the main "on/off" button matches the only plug available.

For a strip, further channels (`1`, `2` ... ) target the specific plugs (power and USB). The details depend on the device, but it is usually *"number of plugs + USB if any (all USB ports are handled together) + 1 main channel"*

The available configuration options are:
- `name` (required): the name of the device, as you want to see it in the switch declaration. The switch will be called `switch.<name>_<channel>`.
- `channels` (required): number of channels. Examples are `1` for a single plug, `6` for a 4 plugs + USB.
- `id` (required): the ID of the device retrieved during MQTT configuration above

In your Home Assistant directory, go to `pyscript` and get the code either by [downloading the latest version](https://github.com/wsw70/meross-local-mqtt/archive/master.zip) or `git clone https://github.com/wsw70/meross-local-mqtt`

Add `arrow` (just this word on a single line) to the file `<config>/pyscript/requirements.txt`. Create the file if it does not exist.

Restart Home Assistant

You should now have devices and entities starting with names defined in `configuration.yaml`

## How it works

A first overview, a bettr description pointing to functions is on the way

![script diagram flow](meross-local-mqtt.png?raw=true)


## Known limitations

- power strips do not have the `0` channel available (in other words, you must switch all the entities). The main reason for that is that adding this channel would, during a restart of the script of HA, first toggle the main switch, and then correctly set all plugs. In practical terms, it means that your lamps that were off would first switch on, and then off during these restarts. I may improva that in the future

- this is not related to meross-local-mqtt, but I noticed that sometimes the Meross strips, when they are online and connected to the MQTT broker, would not connect back if the broker is restarted. This seems not to happen with single plugs. It is probably a firmware problem and maybe related to https://github.com/albertogeniola/meross-homeassistant/issues/180 ? 

## TODOs

- [x] ~~document the way this thing works~~
- [ ] add configuration options at `configuration.yaml` level
- [ ] fix the missing main channel for strips
- [ ] find a way to read the manually configured names (via the UI) to have more useful logs (not only technical names with IDs and channels)
- [x] ~~correctly comment the code~~
- [x] ~~rebuild the list of switches at HA startup (to remove switches that changed or were removed in the configuration)~~
- [x] ~~a new switch must be once manually switched in order to kick off the availability, there should be a better way to do that (probably listening to the startup messages, something about the device clock IIRC)~~
- [x] ~~once a switch is available; it stays available. There are no WILL messages in what is sent by the switch so something else must be done (a regular request for device information I think)~~
- [x] ~~test on a power strip because I do not know what kind of messages they send in the payload (complete status? just the changes? etc.)~~

## Acknowledgements

- [@bytespider](https://github.com/bytespider)  for the tools to pair a Meross device with a local MQTT broker (https://github.com/bytespider/Meross)
- [@craigbarratt](https://github.com/craigbarratt) for the wonderful `pyscript` ((https://github.com/custom-components/pyscript))
- [@albertogeniola](https://github.com/albertogeniola)  for his cloud Meross integration with Home Assistant (https://github.com/albertogeniola/meross-homeassistant)
