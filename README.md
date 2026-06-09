# Robot Control Panel

A lightweight web control panel for the dual-arm robot (arm + dexterous hands +
gripper) and the wok. Runs as a small local web server — open it from any browser
on the same network, including a phone or tablet.

- **One page, three sections:** Dual Arm · Hands & Gripper · Wok
- **English / 中文** toggle
- Live connection status, smooth pose replay with contact-aware motion,
  gripper/hand control, and full wok control (heating, rotation, tilt, spray,
  wash, seasoning dispense)
- No web framework — pure Python standard library + a single HTML page

## Requirements

- Python 3.10+
- The robot reachable on the network (arm over TCP, gripper over USB serial,
  hands over CAN) — see **Configuration** below.

## Setup

```bash
git clone <your-repo-url> robot-web-control
cd robot-web-control

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Add your wok credentials before starting

The wok needs your NextRobot account credentials. Easiest way: start the app, open
the **Wok** section → **Wok Setup**, enter your **Client ID**, **Client Secret**, and
**Restaurant ID** (plus a **Machine ID** if you have more than one machine), and **Save**.

Or set them in a file instead:

```bash
cp config/wok_credentials.example.json config/wok_credentials.json
# edit config/wok_credentials.json with your client_id / client_secret / restaurant_id
```

(The arm, hands, and gripper don't need this.)

## Run

```bash
python web_control.py
```

Then open **http://localhost:8090** on this machine, or
**http://<this-pc-ip>:8090** from another device on the same network.

(Or just `./run.sh`.)

## Using it

1. In the **Dual Arm** section press **Connect** — this also brings up the hands
   and gripper if they're available.
2. Press **Initialize** to enable the arms, ease them to zero, and run the
   startup pose.
3. From there: open/close the hands and gripper, run **Test**, or control the wok.

Connection details (arm IP, gripper serial port, hand CAN interface and bitrate)
live in `config/` — edit `config/hardware_config.json` for your setup.

### Hardware bring-up notes

- **Hands (CAN):** bring the CAN interface up first, e.g.
  `sudo ip link set can0 up type can bitrate 1000000`
- **Gripper (serial):** make sure the user can access the serial device
  (e.g. add yourself to the `dialout` group).

## Notes

- This program **owns the robot hardware** while running — run only one
  controller against the robot at a time.
- **Ctrl+C** eases the arms to zero (contact-aware) and disables them, then quits.
  Press **Ctrl+C again** to force-stop immediately.
- The wok controls talk to a cloud API and need internet access; the arm, hands,
  and gripper work on a LAN-only machine.

## Layout

```
web_control.py        # server + JSON API (stdlib only)
web_control_ui.html   # the single-page UI
config/               # settings, hardware config, startup pose
data/                 # saved poses / steps
hardware/             # arm / hand / gripper controllers
libs/                 # vendored hardware SDKs (arm + LinkerHand)
```
