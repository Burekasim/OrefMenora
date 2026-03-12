# Menora 🕯️

A Python script that listens for rocket/missile siren alerts from the IDF Home Front Command (פיקוד העורף) and flashes a Yeelight smart bulb red, then switches to bright white light.

## How it works

The script polls the IDF Home Front Command (פיקוד העורף) alert API every 2 seconds. When a siren is detected in any of the configured cities, it flashes the bulb red for 5 seconds and then turns on bright white light — giving you a visual warning even if you're wearing headphones or in a noisy environment.

> **Note:** The IDF Home Front Command website and API (`oref.org.il`) are accessible **from Israel only**. If you are outside Israel, the API will not return alerts.

## Hardware

You need a **Yeelight smart bulb** with LAN control support.

The bulb used in this project: [Yeelight Smart Bulb — KSP ₪87](https://ksp.co.il/web/item/272017)

## Setup

### 1. Install the bulb and enable LAN control

After installing the bulb and setting it up via the Yeelight app, you **must enable LAN control** — it is disabled by default.

Follow the instructions here: https://home.yeelight.de/en/support/lan-control/

Once enabled, the bulb will accept direct TCP commands on your local network.

### 2. Find your bulb's IP address

Check your router's DHCP table or the Yeelight app to find the bulb's local IP address. It's recommended to assign it a static IP.

### 3. Install dependencies

```bash
pip install yeelight requests
```

Or using the requirements file:

```bash
pip install -r requirements.txt
```

### 4. Configure

Edit the top of `menora.py`:

```python
BULB_IP       = "192.168.x.x"         # your bulb's local IP
TARGET_CITIES = ["קריית אונו", "גדרה"]        # list of cities to watch
FLASH_SECONDS = 5                     # how long to flash red
```

### 5. Run

```bash
python3 menora.py
```

Test that the bulb reacts correctly before relying on it:

```bash
python3 menora.py --test
```

This triggers the flash sequence immediately without waiting for a real alert.

## Rate limiting

If the API returns HTTP 429 (too many requests), the poll interval automatically backs off from 2s → 3s → 6s → 9s and resets back to 2s after 5 minutes.

## Requirements

- Python 3.6+
- `yeelight`
- `requests`
- The script must run on a machine that is **on the same local network** as the bulb
- Must be run **from within Israel** to receive live alerts from the IDF Home Front Command API
