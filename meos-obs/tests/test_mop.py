from meos_obs import views
from meos_obs.mock_meos import MockMeosServer, Simulation
from meos_obs.mop import MopState

COMPLETE = """<?xml version="1.0" encoding="UTF-8"?>
<MOPComplete xmlns="http://www.melin.nu/mop" nextdifference="7">
<competition date="2026-10-03" organizer="X" homepage="" zerotime="10:00:00">Test-OL</competition>
<ctrl id="31">31</ctrl><ctrl id="45">45</ctrl>
<cls id="1" ord="10" radio="31,45" len="5200">H21</cls>
<org id="1">OLV Süd</org>
<cmp id="1" card="123"><base org="1" cls="1" stat="1" st="360000" rt="30000">Anna A</base>
  <radio>31,9000;45,20000</radio><input it="0" tstat="1"/></cmp>
<cmp id="2" card="124" competing="true"><base org="1" cls="1" stat="0" st="361200" rt="0">Ben B</base>
  <radio>31,8000</radio><input it="0" tstat="1"/></cmp>
</MOPComplete>"""

DIFF = """<MOPDiff xmlns="http://www.melin.nu/mop" nextdifference="8">
<cmp id="1" delete="true"/>
<cmp id="2"><base org="1" cls="1" stat="1" st="361200" rt="28000">Ben B</base></cmp>
</MOPDiff>"""


def test_complete_and_diff():
    s = MopState()
    assert s.apply(COMPLETE) == "7"
    assert s.competition["name"] == "Test-OL"
    assert s.classes[1].radio == [[31, 45]]
    assert s.competitors[1].radio == {31: 9000, 45: 20000}

    res = views.class_results(s, 1)
    assert [r["name"] for r in res["rows"]] == ["Anna A", "Ben B"]
    assert res["rows"][1]["state"] == "running"
    assert res["rows"][1]["splits"][0]["rank"] == 1  # 8000 < 9000

    assert s.apply(DIFF) == "8"
    assert 1 not in s.competitors
    ben = s.competitors[2]
    assert ben.stat == 1 and ben.rt == 28000
    assert ben.radio == {31: 8000}  # radio fehlt im Diff -> bleibt erhalten
    assert ben.card == 124
    assert not ben.competing
    assert ben.finished_seen and ben.finished_seen > 0  # neu im Ziel

    res = views.class_results(s, 1)
    assert res["rows"][0]["place"] == 1 and res["rows"][0]["time"] == "46:40"
    assert views.ticker(s)[0]["name"] == "Ben B"


def _as_dict(state: MopState):
    def strip(o):
        d = dict(vars(o))
        d.pop("finished_seen", None)
        return d
    return (
        state.competition,
        {k: strip(v) for k, v in state.classes.items()},
        {k: strip(v) for k, v in state.competitors.items()},
        {k: strip(v) for k, v in state.teams.items()},
    )


def test_diffs_equal_complete_over_simulation():
    """Viele Diffs hintereinander müssen denselben Zustand ergeben wie ein frischer Komplettabzug."""
    sim = Simulation(speed=1.0)
    server = MockMeosServer(sim)
    t = sim.sim0
    sim.now = lambda: t  # Zeit manuell steuern

    incremental = MopState()
    nxt = incremental.apply(server.difference("zero"))
    for _ in range(130):
        t += 600  # +1 Minute
        nxt = incremental.apply(server.difference(nxt))

    fresh = MopState()
    fresh.apply(server.difference("zero"))
    assert _as_dict(incremental) == _as_dict(fresh)

    # Plausibilität der Auswertungen
    for cls in views.classes_list(fresh):
        res = views.class_results(fresh, cls["id"])
        assert res is not None
    relay = views.class_results(fresh, 10)
    assert relay["type"] == "team" and relay["legs"] == 3
    assert any(r["state"] == "finished" for r in relay["rows"])
    assert views.ticker(fresh, 5)


def test_unknown_difference_returns_error():
    server = MockMeosServer(Simulation())
    assert server.difference("999").startswith("Error (MeOS)")
