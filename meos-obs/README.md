# MeOS → OBS Live-Anzeige

Holt Live-Daten aus [MeOS](https://www.melin.nu/meos/) über den eingebauten
**Informationsserver** und zeigt sie als Vollbild-Szene (1920×1080) in OBS an:

- Ergebnisliste pro Klasse inkl. **Zwischenzeiten an Funkposten** (Zeit + Platz, Bestzeit grün)
- Läufer „im Wald“ mit Rückstand am letzten Funkposten
- **Staffeln/Teams**: Strecken, Streckenzeit/-platz, Gesamtzeit nach Strecke
- **Ticker „Letzte Zieleinläufe“** (neue Einläufe werden hervorgehoben)
- **Automatische Rotation** durch die Klassen (mit Seitenumbruch bei langen Listen)
  *und* manuelle Auswahl über eine Regie-Seite

```
MeOS (Windows, Hauptrechner)  ──LAN──▶  Python-Server (Arch-Laptop)  ──▶  OBS Browser-Quelle
  Informationsserver :2009                 /overlay   /control   /api/*
```

## Funktionsweise

Der Server fragt alle 2 s `http://<meos>:2009/meos?difference=<id>` ab.
Die erste Abfrage (`difference=zero`) liefert den kompletten Wettkampf (`MOPComplete`),
danach liefert MeOS nur noch Änderungen (`MOPDiff`). Das ist dasselbe Format
(MeOS Online Protocol), das MeOS auch für Online-Ergebnisdienste nutzt.
Startet MeOS neu, wird automatisch wieder komplett geladen.

Es wird nur gelesen, MeOS wird nicht verändert.

## Installation (Arch Linux)

```bash
sudo pacman -S python
cd meos-obs
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## In MeOS den Informationsserver starten

MeOS → Reiter **Dienste** (engl. „Services“) → **Informationsserver** →
„Automatischen Dienst starten“. Standard-Port ist `2009`. In der Windows-Firewall
eingehende Verbindungen auf diesem Port erlauben.

Test vom Laptop aus:

```bash
curl "http://<ip-des-meos-rechners>:2009/meos?get=status"
```

Kommt XML zurück (`<status .../>`), passt alles.

## Starten

```bash
.venv/bin/python -m meos_obs --meos http://<ip-des-meos-rechners>:2009/meos
```

| URL | Zweck |
|-----|-------|
| `http://127.0.0.1:8080/overlay` | OBS **Browser-Quelle** (Breite 1920, Höhe 1080) |
| `http://127.0.0.1:8080/control` | Regie: Rotation/feste Klasse, Ticker, Sekunden pro Seite |

Optionen: `--poll 2` (Abfrageintervall), `--port 8080`,
`--host 0.0.0.0` (Regie-Seite auch vom Handy/Tablet im LAN bedienen).

Overlay-URL-Parameter: `?class=<id>` (feste Klasse, unabhängig von der Regie),
`?ticker=0`, `?transparent=1`. So lassen sich auch mehrere Szenen mit
unterschiedlichen Ansichten bauen.

### OBS-Hinweis (Arch)

Die Browser-Quelle muss in OBS verfügbar sein. Falls sie fehlt: die Flatpak-Version
(`com.obsproject.Studio`) oder ein AUR-Paket mit Browser-Unterstützung verwenden.
Notlösung: Overlay in Chromium im Vollbild/Kiosk-Modus öffnen und per
Fenster-Aufnahme einbinden.

## Testen ohne MeOS (Simulation)

```bash
.venv/bin/python -m meos_obs --demo            # Simulation, 10-facher Zeitraffer
.venv/bin/python -m meos_obs --demo --demo-speed 30
```

Simuliert einen Wettkampf mit 5 Einzelklassen (mit Funkposten, Fehlstempel,
Aufgaben, Nichtstarter) und einer 3er-Staffel. Der Simulator spricht exakt das
MeOS-Differenzprotokoll, d. h. der echte Abfrage-Code wird mitgetestet.

Netzwerk-Test mit getrenntem Simulator (z. B. auf einem anderen Rechner):

```bash
.venv/bin/python -m meos_obs.mock_meos --host 0.0.0.0 --port 2009
.venv/bin/python -m meos_obs --meos http://<ip>:2009/meos
```

Unit-Tests: `.venv/bin/pip install pytest && .venv/bin/python -m pytest`

## Checkliste Wettkampftag

1. Laptop per LAN im Netz, IP des MeOS-Rechners bekannt
2. In MeOS Informationsserver starten, Firewall-Port freigeben
3. `curl …/meos?get=status` vom Laptop aus testen
4. `python -m meos_obs --meos …` starten, `/control` öffnen → „verbunden“
5. In MeOS prüfen, dass die Funkposten als Funkposten markiert sind
   (sonst gibt es keine Zwischenzeitspalten)
6. In OBS Browser-Quelle `http://127.0.0.1:8080/overlay` (1920×1080) anlegen

Der grüne Punkt unten rechts im Overlay wird rot, wenn länger als 15 s keine
Daten von MeOS kamen.
