from drivecheck.model import ActorState, Frame, Lane, Road, Scenario, Section

DT = 0.1


def three_lanes(limit=None, no_passing=False, length=3000.0):
    sections = [Section(0.0, length, limit, no_passing)] if (limit or no_passing) else []
    return Road(length, [Lane(i, (i - 1) * 3.5, 3.5) for i in (1, 2, 3)], sections)


def track(id, x0, y, speed_kmh, n, kind="car", indicator=None, ys=None, **size):
    v = speed_kmh / 3.6
    states = []
    for i in range(n):
        states.append(ActorState(
            id=id, kind=kind, x=x0 + v * DT * i,
            y=ys[i] if ys is not None else y, speed=v,
            indicator=indicator[i] if indicator else "off", **size))
    return states


def scenario(host, *others, road=None, name="test"):
    road = road or three_lanes()
    frames = [Frame(round(i * DT, 3), h, tuple(o[i] for o in others))
              for i, h in enumerate(host)]
    return Scenario(name, road, DT, frames)
