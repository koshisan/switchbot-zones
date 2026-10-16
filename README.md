# SwitchBot Zones

[![Validate](https://github.com/koshisan/switchbot-zones/actions/workflows/validate.yml/badge.svg)](https://github.com/koshisan/switchbot-zones/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-custom-41BDF5.svg)](https://hacs.xyz)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Home Assistant integration that splits the **SwitchBot RGBICWW Floor Lamp**
(W1102004) into several `light` entities, one per zone, and blends the
segments between them into a gradient. A scene can then put a different
colour at the bottom, middle and top of the lamp.

Runs alongside the core SwitchBot integration. It does not replace it and does
not touch it.

> ### Scope
>
> Built for, and only run against, the RGBICWW Floor Lamp. Other RGBIC SwitchBot
> lights probably speak the same segment protocol, but that is untested.

## The problem this solves

The core integration, the SwitchBot cloud API and Matter can all set exactly one
colour for the whole lamp. The lamp itself has 21 individually addressable
segments. This integration writes those segments directly over Bluetooth and
hands Home Assistant a few perfectly ordinary colour lights.

## Requirements

- The lamp's encryption key. If the lamp is already in the core SwitchBot
  integration, the key is taken from there.
- A **connectable** Bluetooth path to the lamp: a local adapter or an ESPHome
  Bluetooth proxy with active connections enabled. Commands go through Home
  Assistant's Bluetooth stack, so any proxy that works for the core integration
  works here.

## Install

### HACS

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/koshisan/switchbot-zones`, category **Integration**
3. Install **SwitchBot Zones**, then restart Home Assistant

### Manual

Copy `custom_components/switchbot_zones/` into your Home Assistant
`config/custom_components/` directory and restart.

## Set up

**Settings → Devices & Services → Add Integration → SwitchBot Zones**, then pick
the lamp from your SwitchBot entries, or choose **Manual** and enter address,
key ID and key.

Either way the key is tested against the lamp before it is saved. A key in the
core SwitchBot entry can be stale — the lamp then answers every command with
status `04`, for the core integration as well. To fix the key of a lamp that is
already set up, run **Add Integration → SwitchBot Zones → Manual** again with
the correct key: the existing entry is updated and reloaded, entities stay.

## Options

Changing options reloads the integration. No Home Assistant restart needed.

| Option | Default | Meaning |
|---|---|---|
| Zones | `0-2, 9-11, 18-20` | Segment ranges, one per zone. The number of ranges is the number of light entities. |
| Blend mode | OKLCH | How the segments between two zones are mixed. |
| Colours per packet | 4 | Segments per Bluetooth write, as the SwitchBot app sends them. |
| Count segments from the bottom | on | Segment 0 and Zone 1 at the floor. Off uses the lamp's own order, which starts at the top. |

Blend modes:

- **RGB** — linear mix of the raw values. Goes grey between opposite colours.
- **HSV** — keeps full saturation, but sweeps through every hue in between and
  brightness jumps.
- **OKLab** — even perceived brightness, opposite colours turn pastel.
- **OKLCH** — even brightness and full saturation. Recommended.

Fading into a zone that is off works in every mode: the gap darkens towards it.

## What you get

One light per zone, named `Zone 1 … Zone N`, with colour, brightness and on/off.
Each carries its segment numbers as the `segments` attribute. The zones appear
on the same device card as the core integration's lamp, so their entity IDs
follow that device's name.

```yaml
scene:
  - name: Sunset lamp
    entities:
      light.switchbot_floor_lamp_zone_1: {state: on, brightness: 255, hs_color: [30, 100]}
      light.switchbot_floor_lamp_zone_2: {state: on, brightness: 255, hs_color: [330, 85]}
      light.switchbot_floor_lamp_zone_3: {state: on, brightness: 200, hs_color: [275, 100]}
```

## How it works

Bluetooth goes through [PySwitchbot](https://github.com/sblibs/pySwitchbot),
which Home Assistant already ships: encryption, retries and connection handling
come from there. The connection is opened on demand and closed a few seconds
after the last command, so the core integration and the SwitchBot app can still
reach the lamp.

A frame is written as:

1. `57 0F 49 0C 01` — switch the lamp to per-segment mode
2. `57 0F 49 0B <meta> RR GG BB …` with up to four colours per packet, `meta`
   being the index of the first segment in the packet with bit `0x80` set

The `0x80` bit has to be on every packet: once the lamp is already in
per-segment mode, it acknowledges packets without it but does not show them.

Details:

- **Every write is a complete frame.** The gaps depend on both neighbouring
  zones, so any change re-renders all 21 segments.
- **Writes are debounced by 150 ms**, so a scene that sets three zones results in
  one frame, not three.
- **Brightness is the V of the colour.** The lamp's global brightness is pinned
  to 100 % when this integration turns it on.
- **External power-off is followed.** The lamp's Bluetooth advertisements carry
  its power state; if something else switches it off, all zones go off.

## Limitations

- **Segment colours cannot be read back**, so zone state is optimistic. If the
  core integration or the app sets a single colour, the zones will not notice
  until the next write from here.
- **No effects, no white channel.** These are static colour zones by design. The
  lamp's own effects and colour temperature stay available through the core
  integration.

## Licence

MIT
