# Menora 🕯️

A Python script that listens for rocket/missile siren alerts from the IDF Home Front Command (פיקוד העורף) and controls a Yeelight smart bulb to give a visual warning.

## Demo

<video src="https://github.com/Burekasim/OrefMenora/raw/refs/heads/main/demo.mp4" controls width="640"></video>

## How it works

The script polls the IDF Home Front Command alert API every 2 seconds.

**On a siren alert (ירי רקטות וטילים / חדירת כלי טיס עוין):**
- Flashes the bulb red for 5 seconds
- Switches to bright white light

**On all-clear (האירוע הסתיים):**
- Blinks the bulb green for 10 seconds
- Restores the bulb to exactly what it was before the alarm (color, brightness, on/off state)

**State preservation:**
- When the script starts, it snapshots the current bulb state (power, color mode, color temperature, RGB, brightness)
- Every 60 minutes while idle, the snapshot is refreshed — so if you manually change the bulb in between, the restore will reflect your latest settings
- After the green blink, the bulb is restored to the most recent snapshot

> **Note:** The IDF Home Front Command API (`oref.org.il`) is accessible **from Israel only**.

## Hardware

You need a **Yeelight smart bulb** with LAN control support.

The bulb used in this project: [Yeelight Smart Bulb — KSP ₪87](https://ksp.co.il/web/item/272017)

## Setup

### 1. Install the bulb and enable LAN control

After installing the bulb and setting it up via the Yeelight app, you **must enable LAN control** — it is disabled by default.

Instructions: https://home.yeelight.de/en/support/lan-control/

Once enabled, the bulb will accept direct TCP commands on your local network.

### 2. Find your bulb's IP address

Check your router's DHCP table or the Yeelight app to find the bulb's local IP. It is recommended to assign a static IP so it doesn't change.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install yeelight requests
```

### 4. Configure

Edit the constants at the top of `menora.py`:

| Variable | Description | Default |
|---|---|---|
| `BULB_IP` | Local IP address of your Yeelight bulb | `172.18.150.107` |
| `TARGET_CITIES` | List of Hebrew city names to watch for | `["קריית אונו", "ונוא תירק"]` |
| `POLL_INTERVAL` | Seconds between API polls | `2` |
| `FLASH_SECONDS` | How long to flash red on a siren alert | `5` |
| `STATE_REFRESH_INTERVAL` | Seconds between passive bulb state snapshots | `3600` (60 min) |

### 5. Run

```bash
python3 menora.py
```

Test that the bulb reacts correctly before relying on it:

```bash
python3 menora.py --test
```

`--test` mode snapshots the current bulb state, triggers the full red-flash → green-blink → restore sequence immediately without waiting for a real alert.

## Alert sequence

```
Siren detected
    → 🚨 Red flash for FLASH_SECONDS
    → 💡 Bright white (stays on until all-clear)

All-clear detected
    → 🟢 Green blink for 10 seconds
    → 🔄 Restore bulb to pre-alarm state (color / brightness / on-off)
```

## Rate limiting

If the API returns HTTP 429 (too many requests), the poll interval automatically backs off:
`2s → 3s → 6s → 9s` and resets back to `2s` after 5 minutes.

## Requirements

- Python 3.6+
- `yeelight`
- `requests`
- Must run on a machine **on the same local network** as the bulb
- Must run **from within Israel** to receive live alerts from the IDF Home Front Command API
