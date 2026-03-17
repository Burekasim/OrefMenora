#!/usr/bin/env python3
"""
Menora — Siren alert light controller
======================================
Polls Pikud HaOref every 2 seconds; when a siren is active in any of the
TARGET_CITIES, flashes the Yeelight bulb red for 5 seconds then switches
to bright white.

Usage:
    python3 menora.py            # start normal polling
    python3 menora.py --test     # trigger a test alert immediately and exit

Configuration (edit at the top of this file):
    BULB_IP        — IP address of the Yeelight bulb on your LAN
    TARGET_CITIES  — list of Hebrew city names to watch for
    POLL_INTERVAL  — seconds between API polls (default: 2)
    FLASH_SECONDS  — how long to flash red on alert (default: 5)

Rate-limit backoff:
    On HTTP 429 the poll interval escalates: 2s → 3s → 6s → 9s.
    It resets back to 2s automatically after 5 minutes.

Requirements:
    pip install yeelight requests
"""

import argparse
import time
import logging
import requests
from yeelight import Bulb, Flow, RGBTransition

# ── Config ────────────────────────────────────────────────────────────────────
BULB_IP          = "192.168.1.123"
TARGET_CITIES    = ["קריית אונו", "גדרה"]
POLL_INTERVAL    = 2    # normal seconds between polls
FLASH_SECONDS    = 5    # how long to flash red
BACKOFF_STEPS    = [3, 6, 9]   # escalating intervals on 429
BACKOFF_RESET    = 300          # seconds until interval resets to normal

POST_ALLCLEAR_HOLD = 180   # seconds to stay lit after green blink before restoring state
STATE_REFRESH_INTERVAL = 3600  # seconds between passive state snapshots (60 min)

ALERT_URL   = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
TITLE_ALL_CLEAR = "האירוע הסתיים"       # "The event has ended" — all-clear signal
TITLES_RED  = {
    "בדקות הקרובות צפויות להתקבל התרעות באזורך",                 # Rocket and missile fire are on the way
    "ירי רקטות וטילים",                                          # Rocket and missile fire
    "חדירת כלי טיס עוין",                                        # Hostile aircraft infiltration
}
HEADERS   = {
    "Referer":          "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Bulb ──────────────────────────────────────────────────────────────────────
def get_bulb_state(bulb):
    """Snapshot the full current state of the bulb.

    Returns a dict with keys: power, bright, color_mode, ct, rgb
      color_mode: 1 = RGB, 2 = color-temp, 3 = HSV
    Returns None if the bulb is unreachable.
    """
    try:
        props = bulb.get_properties()
        state = {
            "power":      props.get("power", "off"),
            "bright":     int(props.get("bright", 100)),
            "color_mode": int(props.get("color_mode", 2)),
            "ct":         int(props.get("ct", 4000)),
            "rgb":        int(props.get("rgb", 16777215)),
        }
        log.info(
            "📸 Bulb state captured — power=%s  mode=%s  bright=%s  ct=%s  rgb=#%06X",
            state["power"], state["color_mode"], state["bright"],
            state["ct"], state["rgb"],
        )
        return state
    except Exception as e:
        log.warning("Could not read bulb state: %s", e)
        return None


def restore_bulb_state(bulb, state):
    """Restore the bulb to a previously captured state."""
    if state is None:
        log.warning("No saved state to restore — leaving bulb as-is")
        return
    log.info(
        "🔄 Restoring bulb state — power=%s  mode=%s  bright=%s  ct=%s  rgb=#%06X",
        state["power"], state["color_mode"], state["bright"],
        state["ct"], state["rgb"],
    )
    if state["power"] == "off":
        bulb_cmd(bulb.turn_off)
        return
    bulb_cmd(bulb.turn_on)
    if state["color_mode"] == 1:   # RGB
        r = (state["rgb"] >> 16) & 0xFF
        g = (state["rgb"] >> 8) & 0xFF
        b = state["rgb"] & 0xFF
        bulb_cmd(bulb.set_rgb, r, g, b)
    else:                           # color-temp (mode 2) or HSV (mode 3, best-effort)
        bulb_cmd(bulb.set_color_temp, state["ct"])
    bulb_cmd(bulb.set_brightness, state["bright"])


def is_bulb_on(bulb):
    """Return True if the bulb is currently powered on."""
    try:
        props = bulb.get_properties()
        return props.get("power") == "on"
    except Exception:
        return False  # assume off / unreachable


def bulb_cmd(fn, *args, **kwargs):
    """Call a bulb command and log any error without raising."""
    try:
        fn(*args, **kwargs)
        return True
    except Exception as e:
        log.error("Bulb command failed (%s): %s", fn.__name__, e)
        return False


def flash_red_then_white(bulb):
    """Flash red for FLASH_SECONDS then switch to full-brightness white."""
    log.info("🚨 SIREN — flashing red for %ds", FLASH_SECONDS)

    # Ensure the bulb is on and at full brightness before starting the flow
    # (it may have been turned off or dimmed via the app)
    bulb_cmd(bulb.turn_on)
    bulb_cmd(bulb.set_brightness, 100)
    time.sleep(0.3)   # brief settle so the bulb accepts the flow command

    # Build infinite red-flash flow: 250 ms full red → 250 ms near-off, loops until stopped
    cycle = [
        RGBTransition(255, 0, 0, duration=250, brightness=100),  # full-power red
        RGBTransition(255, 0, 0, duration=250, brightness=1),     # near-off
    ]
    bulb_cmd(bulb.start_flow, Flow(count=0, transitions=cycle))   # count=0 → infinite
    time.sleep(FLASH_SECONDS)
    bulb_cmd(bulb.stop_flow)

    log.info("💡 Alert period done — switching to bright white")
    bulb_cmd(bulb.set_color_temp, 6500)   # cool white
    bulb_cmd(bulb.set_brightness, 100)
    bulb_cmd(bulb.turn_on)


def blink_green_then_white(bulb, original_state):
    """Blink green for 5 seconds (all-clear signal), hold steady green for
    the remainder of POST_ALLCLEAR_HOLD, then restore the bulb to original_state."""
    log.info("🟢 ALL CLEAR — blinking green for 5s then holding green for %ds", POST_ALLCLEAR_HOLD)

    bulb_cmd(bulb.turn_on)
    bulb_cmd(bulb.set_brightness, 100)
    time.sleep(0.3)

    cycle = [
        RGBTransition(0, 255, 0, duration=500, brightness=100),  # full green
        RGBTransition(0, 255, 0, duration=500, brightness=5),    # near-off
    ]
    bulb_cmd(bulb.start_flow, Flow(count=0, transitions=cycle))
    time.sleep(5)
    bulb_cmd(bulb.stop_flow)

    log.info("🟢 Holding steady green for %ds", POST_ALLCLEAR_HOLD)
    bulb_cmd(bulb.set_rgb, 0, 255, 0)
    bulb_cmd(bulb.set_brightness, 100)
    bulb_cmd(bulb.turn_on)
    time.sleep(POST_ALLCLEAR_HOLD)

    restore_bulb_state(bulb, original_state)


# ── Polling ───────────────────────────────────────────────────────────────────
def fetch_alert():
    """Return (title, cities) for the current alert, or (None, []) if no alert."""
    r = requests.get(ALERT_URL, headers=HEADERS, timeout=5)
    r.raise_for_status()
    r.encoding = 'utf-8-sig'
    text = r.text.strip()
    if not text:
        return None, []
    try:
        payload = r.json()
    except ValueError:
        return None, []
    return payload.get("title"), payload.get("data", [])


def main():
    bulb          = Bulb(BULB_IP)
    alerting      = False   # True while we're mid-alert (prevents re-triggering)
    backoff_idx   = 0       # index into BACKOFF_STEPS (0 = no backoff)
    backoff_since = None    # time when backoff started

    log.info("Menora started — watching for sirens in %s  (bulb: %s)", TARGET_CITIES, BULB_IP)

    # Snapshot the bulb state at startup so we can restore it after an all-clear
    original_state     = get_bulb_state(bulb)
    last_snapshot_time = time.monotonic()

    while True:
        # Reset backoff to normal after BACKOFF_RESET seconds
        if backoff_idx > 0 and (time.monotonic() - backoff_since) >= BACKOFF_RESET:
            backoff_idx = 0
            backoff_since = None
            log.info("↩️  Poll interval reset to %ds", POLL_INTERVAL)

        interval = BACKOFF_STEPS[backoff_idx - 1] if backoff_idx > 0 else POLL_INTERVAL

        # Refresh the snapshot every 60 min while the bulb is in its normal state
        # (not mid-alert), so we always restore to the latest user-set state
        if not alerting and (time.monotonic() - last_snapshot_time) >= STATE_REFRESH_INTERVAL:
            log.info("⏱️  60-min state refresh")
            original_state     = get_bulb_state(bulb)
            last_snapshot_time = time.monotonic()

        try:
            # Don't query bulb state during an active alert — use the pre-alert snapshot
            if not alerting and not is_bulb_on(bulb):
                log.debug("💡 Bulb is off (will turn on before any alert)")

            title, cities = fetch_alert()

            hit = [c for c in TARGET_CITIES if c in cities]
            if hit:
                if title == TITLE_ALL_CLEAR:
                    # All-clear must be handled even while alerting=True (it arrives
                    # AFTER the siren, so alerting is always True at this point).
                    if alerting:
                        log.info("🟢 ALL CLEAR in %s", hit)
                        blink_green_then_white(bulb, original_state)
                        alerting = False
                        last_snapshot_time = time.monotonic()  # don't re-snapshot right after restore
                elif title in TITLES_RED:
                    if not alerting:
                        alerting = True
                        log.info("🚨 SIREN in %s — title: %s", hit, title)
                        flash_red_then_white(bulb)
                else:
                    if not alerting:
                        alerting = True
                        log.info("⚠️  Unknown alert in %s — title: %s (no light action)", hit, title)
            else:
                if not alerting:
                    alerting = False

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                new_idx = min(backoff_idx + 1, len(BACKOFF_STEPS))
                if new_idx != backoff_idx:
                    backoff_idx = new_idx
                    backoff_since = time.monotonic()
                    interval = BACKOFF_STEPS[backoff_idx - 1]
                    log.warning("⚠️  429 Too Many Requests — slowing to %ds (resets in %ds)",
                                interval, BACKOFF_RESET)
            else:
                log.warning("Network error fetching alerts: %s", e)
        except requests.exceptions.RequestException as e:
            log.warning("Network error fetching alerts: %s", e)
        except Exception as e:
            log.error("Bulb or unexpected error: %s", e)

        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Menora siren light controller")
    parser.add_argument("--test", action="store_true", help="Trigger a test alert immediately without polling")
    args = parser.parse_args()

    if args.test:
        log.info("🧪 Test mode — triggering alert now")
        try:
            bulb = Bulb(BULB_IP)
            original_state = get_bulb_state(bulb)
            flash_red_then_white(bulb)
            blink_green_then_white(bulb, original_state)
            log.info("✅ Test complete")
        except Exception as e:
            log.error("Test failed: %s", e)
    else:
        while True:
            try:
                main()
            except Exception as e:
                log.error("Unhandled error in main loop, restarting in 5s: %s", e)
                time.sleep(5)
