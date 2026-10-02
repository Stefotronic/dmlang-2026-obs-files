"""Aufbereitung des MOP-Zustands zu anzeigefertigen Daten (JSON)."""
from __future__ import annotations

import time

from .mop import (
    STATUS_DQ,
    STATUS_MAX,
    STATUS_MP,
    STATUS_DNF,
    STATUS_NO_TIMING,
    STATUS_OK,
    STATUS_OUT_OF_COMPETITION,
    STATUS_TEXT,
    STATUS_UNKNOWN,
    ClassInfo,
    Competitor,
    MopState,
    Team,
)

NEW_SECONDS = 45
# Status, die mit Statustext am Ende der Ergebnisliste erscheinen
TAIL_STATUSES = {STATUS_MP, STATUS_DNF, STATUS_DQ, STATUS_MAX, STATUS_NO_TIMING, STATUS_OUT_OF_COMPETITION}


def fmt_time(ds: int) -> str:
    if ds <= 0:
        return ""
    s = ds // 10
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_behind(ds: int) -> str:
    return "+" + fmt_time(ds) if ds > 0 else ""


def fmt_tod(ds: int) -> str:
    if ds < 0:
        return ""
    s = (ds // 10) % 86400
    return f"{s // 3600:02d}:{(s // 60) % 60:02d}:{s % 60:02d}"


def _places(values: list[int]) -> list[int]:
    """Platzierungen für eine aufsteigend sortierte Liste (gleiche Zeit = gleicher Platz)."""
    places: list[int] = []
    for i, v in enumerate(values):
        places.append(places[-1] if i and values[i - 1] == v else i + 1)
    return places


def _rank(value: int, all_values: list[int]) -> int:
    return 1 + sum(1 for v in all_values if v < value)


def _is_new(c: Competitor, now: float) -> bool:
    return bool(c.finished_seen) and now - (c.finished_seen or 0) < NEW_SECONDS


def _org_name(state: MopState, org_id: int) -> str:
    org = state.orgs.get(org_id)
    return org.name if org else ""


def _control_name(state: MopState, ctrl_id: int) -> str:
    ctrl = state.controls.get(ctrl_id)
    return ctrl.name if ctrl and ctrl.name else str(ctrl_id)


def _is_team_class(state: MopState, cls_id: int) -> bool:
    return any(t.cls == cls_id for t in state.teams.values())


def classes_list(state: MopState) -> list[dict]:
    result = []
    for cls in sorted(state.classes.values(), key=lambda c: (c.order, c.name)):
        is_team = _is_team_class(state, cls.id)
        runners = [c for c in state.competitors.values() if c.cls == cls.id]
        finished = sum(1 for c in runners if c.stat == STATUS_OK and c.rt > 0)
        running = sum(1 for c in runners if c.stat == STATUS_UNKNOWN and (c.competing or c.radio))
        if is_team:
            teams = [t for t in state.teams.values() if t.cls == cls.id]
            entries = len(teams)
            finished = sum(1 for t in teams if t.stat == STATUS_OK and t.rt > 0)
            running = sum(
                1 for t in teams
                if t.stat == STATUS_UNKNOWN and any(
                    (r := state.competitors.get(rid)) and (r.competing or r.radio or r.rt > 0)
                    for leg in t.legs for rid in leg))
        else:
            entries = len(runners)
        result.append(
            {
                "id": cls.id,
                "name": cls.name,
                "type": "team" if is_team else "individual",
                "entries": entries,
                "finished": finished,
                "running": running,
                "active": finished + running > 0,
            }
        )
    return result


def class_results(state: MopState, cls_id: int) -> dict | None:
    cls = state.classes.get(cls_id)
    if cls is None:
        return None
    if _is_team_class(state, cls_id):
        return _team_results(state, cls)
    return _individual_results(state, cls)


def _individual_results(state: MopState, cls: ClassInfo) -> dict:
    now = time.time()
    radios = cls.radio[0] if cls.radio else []
    runners = [c for c in state.competitors.values() if c.cls == cls.id]

    split_times = {
        ctrl: [c.radio[ctrl] for c in runners if ctrl in c.radio and c.stat in (STATUS_UNKNOWN, STATUS_OK)]
        for ctrl in radios
    }
    best_split = {ctrl: min(v) for ctrl, v in split_times.items() if v}

    finished = sorted((c for c in runners if c.stat == STATUS_OK and c.rt > 0), key=lambda c: c.rt)
    running = [c for c in runners if c.stat == STATUS_UNKNOWN and (c.competing or c.radio)]
    tail = [c for c in runners if c.stat in TAIL_STATUSES]

    def progress(c: Competitor) -> tuple[int, int]:
        passed = [i for i, ctrl in enumerate(radios) if ctrl in c.radio]
        if not passed:
            return (0, c.st)
        last = passed[-1]
        return (-(last + 1), c.radio[radios[last]])

    running.sort(key=progress)
    tail.sort(key=lambda c: (c.stat, c.rt or 10**9))

    def splits(c: Competitor) -> list[dict]:
        out = []
        for ctrl in radios:
            t = c.radio.get(ctrl)
            if not t:
                out.append({"time": "", "rank": None, "best": False})
                continue
            valid = c.stat in (STATUS_UNKNOWN, STATUS_OK)
            rank = _rank(t, split_times[ctrl]) if valid else None
            out.append({"time": fmt_time(t), "rank": rank, "best": rank == 1})
        return out

    def base_row(c: Competitor) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "org": _org_name(state, c.org),
            "bib": c.bib,
            "splits": splits(c),
            "new": _is_new(c, now),
        }

    rows = []
    best = finished[0].rt if finished else 0
    for c, place in zip(finished, _places([c.rt for c in finished])):
        rows.append(base_row(c) | {
            "state": "finished",
            "place": place,
            "time": fmt_time(c.rt),
            "behind": fmt_behind(c.rt - best),
            "status": "",
            "prel": c.prel,
        })
    for c in running:
        last_ctrl = next((ctrl for ctrl in reversed(radios) if ctrl in c.radio), None)
        info = ""
        if last_ctrl is not None:
            t = c.radio[last_ctrl]
            behind = fmt_behind(t - best_split[last_ctrl]) if last_ctrl in best_split else ""
            info = f"{_control_name(state, last_ctrl)}: {behind or 'führt'}"
        rows.append(base_row(c) | {
            "state": "running",
            "place": None,
            "time": "",
            "behind": "",
            "status": "im Wald",
            "info": info.strip(),
        })
    for c in tail:
        rows.append(base_row(c) | {
            "state": "other",
            "place": None,
            "time": fmt_time(c.rt) if c.stat in (STATUS_OUT_OF_COMPETITION, STATUS_MP) else "",
            "behind": "",
            "status": STATUS_TEXT.get(c.stat, ""),
        })

    return {
        "id": cls.id,
        "name": cls.name,
        "type": "individual",
        "length": cls.length,
        "controls": [{"id": ctrl, "name": _control_name(state, ctrl)} for ctrl in radios],
        "rows": rows,
        "counts": {"finished": len(finished), "running": len(running), "entries": len(runners)},
    }


def _team_results(state: MopState, cls: ClassInfo) -> dict:
    now = time.time()
    teams = [t for t in state.teams.values() if t.cls == cls.id]
    n_legs = max((len(t.legs) for t in teams), default=0)

    def leg_runner(t: Team, leg: int) -> Competitor | None:
        if leg >= len(t.legs):
            return None
        for rid in t.legs[leg]:
            if rid in state.competitors:
                return state.competitors[rid]
        return None

    # Strecken- und Zwischenplatzierung (Gesamtzeit nach Strecke) je Strecke
    leg_times: list[list[int]] = []
    cum_times: list[list[int]] = []
    for leg in range(n_legs):
        lt, ct = [], []
        for t in teams:
            r = leg_runner(t, leg)
            if r and r.stat == STATUS_OK and r.rt > 0:
                lt.append(r.rt)
                if r.tstat in (STATUS_OK, STATUS_UNKNOWN) or leg == 0:
                    ct.append(r.it + r.rt)
        leg_times.append(lt)
        cum_times.append(ct)

    def legs_info(t: Team) -> tuple[list[dict], int, int, str]:
        cells = []
        done = 0
        cum = 0
        info = ""
        for leg in range(n_legs):
            r = leg_runner(t, leg)
            if r is None:
                cells.append({"name": "", "time": "", "rank": None, "cum": "", "cum_rank": None, "state": "empty"})
                continue
            cell = {"name": r.name, "time": "", "rank": None, "cum": "", "cum_rank": None,
                    "state": "waiting", "new": _is_new(r, now)}
            if r.stat == STATUS_OK and r.rt > 0:
                c = r.it + r.rt
                cell.update(state="finished", time=fmt_time(r.rt), rank=_rank(r.rt, leg_times[leg]),
                            cum=fmt_time(c), cum_rank=_rank(c, cum_times[leg]) if c in cum_times[leg] else None)
                done = leg + 1
                cum = c
            elif r.stat in TAIL_STATUSES:
                cell.update(state="other", time=STATUS_TEXT.get(r.stat, ""))
            elif r.competing or r.radio:
                cell.update(state="running", time="läuft")
                radios = cls.radio[leg] if leg < len(cls.radio) else []
                last_ctrl = next((x for x in reversed(radios) if x in r.radio), None)
                if last_ctrl is not None:
                    info = f"Str. {leg + 1} · {_control_name(state, last_ctrl)}: {fmt_time(r.it + r.radio[last_ctrl])}"
                    cell["time"] = f"{_control_name(state, last_ctrl)} {fmt_time(r.radio[last_ctrl])}"
                elif not info:
                    info = f"Str. {leg + 1} läuft"
            cells.append(cell)
        return cells, done, cum, info

    finished, running, tail = [], [], []
    for t in teams:
        cells, done, cum, info = legs_info(t)
        entry = (t, cells, done, cum, info)
        if t.stat == STATUS_OK and t.rt > 0:
            finished.append(entry)
        elif t.stat in TAIL_STATUSES:
            tail.append(entry)
        elif t.stat == STATUS_UNKNOWN and any(c["state"] != "waiting" and c["state"] != "empty" for c in cells):
            running.append(entry)

    finished.sort(key=lambda e: e[0].rt)
    running.sort(key=lambda e: (-e[2], e[3]))
    tail.sort(key=lambda e: e[0].stat)

    rows = []
    best = finished[0][0].rt if finished else 0
    for (t, cells, *_), place in zip(finished, _places([e[0].rt for e in finished])):
        rows.append({"id": t.id, "name": t.name, "org": _org_name(state, t.org), "bib": t.bib, "legs": cells,
                     "state": "finished", "place": place, "time": fmt_time(t.rt),
                     "behind": fmt_behind(t.rt - best), "status": "",
                     "new": any(c.get("new") for c in cells)})
    for t, cells, done, cum, info in running:
        rows.append({"id": t.id, "name": t.name, "org": _org_name(state, t.org), "bib": t.bib, "legs": cells,
                     "state": "running", "place": None, "time": "", "behind": "",
                     "status": "unterwegs", "info": info,
                     "new": any(c.get("new") for c in cells)})
    for t, cells, *_ in tail:
        rows.append({"id": t.id, "name": t.name, "org": _org_name(state, t.org), "bib": t.bib, "legs": cells,
                     "state": "other", "place": None, "time": "", "behind": "",
                     "status": STATUS_TEXT.get(t.stat, ""), "new": False})

    return {
        "id": cls.id,
        "name": cls.name,
        "type": "team",
        "length": cls.length,
        "legs": n_legs,
        "rows": rows,
        "counts": {"finished": len(finished), "running": len(running), "entries": len(teams)},
    }


def ticker(state: MopState, limit: int = 12) -> list[dict]:
    now = time.time()
    team_of: dict[int, tuple[Team, int]] = {}
    for t in state.teams.values():
        for leg, rids in enumerate(t.legs):
            for rid in rids:
                team_of[rid] = (t, leg)

    finishers = [c for c in state.competitors.values() if c.finished_seen is not None]
    finishers.sort(key=lambda c: (c.finished_seen or 0, c.finish_tod), reverse=True)
    finishers = finishers[:limit]

    place_cache: dict[int, dict[int, int]] = {}

    def place_of(c: Competitor) -> int | None:
        if c.stat != STATUS_OK:
            return None
        if c.cls not in place_cache:
            res = class_results(state, c.cls)
            place_cache[c.cls] = {
                r["id"]: r["place"] for r in (res["rows"] if res and res["type"] == "individual" else [])
                if r["place"]
            }
        return place_cache[c.cls].get(c.id)

    items = []
    for c in finishers:
        cls = state.classes.get(c.cls)
        team = team_of.get(c.id)
        items.append({
            "id": c.id,
            "name": c.name,
            "org": _org_name(state, c.org),
            "class": cls.name if cls else "",
            "time": fmt_time(c.rt),
            "finish": fmt_tod(c.finish_tod),
            "status": "" if c.stat == STATUS_OK else STATUS_TEXT.get(c.stat, ""),
            "place": None if team else place_of(c),
            "team": f"{team[0].name} · Str. {team[1] + 1}" if team else "",
            "new": _is_new(c, now),
        })
    return items
