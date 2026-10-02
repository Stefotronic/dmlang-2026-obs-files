"""Start: python -m meos_obs --meos http://<meos-rechner>:2009/meos"""
from __future__ import annotations

import argparse
import logging

import uvicorn

from .server import create_app


def main() -> None:
    p = argparse.ArgumentParser(description="MeOS-Live-Daten als OBS-Browser-Quelle")
    p.add_argument("--meos", help="URL des MeOS-Informationsservers, z. B. http://192.168.1.10:2009/meos")
    p.add_argument("--demo", action="store_true", help="Eingebauten MeOS-Simulator statt echtem MeOS verwenden")
    p.add_argument("--demo-speed", type=float, default=10.0, help="Zeitraffer-Faktor der Simulation")
    p.add_argument("--poll", type=float, default=2.0, help="Abfrageintervall in Sekunden (Standard 2)")
    p.add_argument("--host", default="127.0.0.1", help="0.0.0.0, um die Regie-Seite im LAN freizugeben")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()

    if not a.meos and not a.demo:
        p.error("--meos URL oder --demo angeben")

    meos_url = a.meos or f"http://127.0.0.1:{a.port}/mock/meos"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(f"MeOS-Quelle : {meos_url}")
    print(f"OBS-Overlay : http://127.0.0.1:{a.port}/overlay")
    print(f"Regie       : http://127.0.0.1:{a.port}/control")
    app = create_app(meos_url, poll_interval=a.poll, demo=a.demo, demo_speed=a.demo_speed)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
