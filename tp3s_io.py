import json
from collections import namedtuple, defaultdict

TestRequest = namedtuple("TestRequest", ["test_id", "release", "deadline", "dur"])
Vehicle = namedtuple("Vehicle", ["vehicle_id", "release"])

# global data info
TEST_MAP = {}
VEHICLE_MAP = defaultdict(list)
REHIT_MAP = {}


def _read_json(filepath):
    with open(filepath) as f:
        data = f.read()
    j = json.loads(data)
    return j


def _parse_test(j):
    tests = []
    data = j["tests"]
    for t in data:
        dur = t["dur"]
        r = t["release"]
        d = t["deadline"]
        i = t["test_id"]
        new_test = TestRequest(i, r, d, dur)
        tests.append(new_test)
    return sorted(tests, key=lambda x: x.test_id)


def _parse_vehicle(j):
    vehicles = []
    data = j["vehicles"]
    for v in data:
        i = v["vehicle_id"]
        r = v["release"]
        new_vehicle = Vehicle(i, r)
        vehicles.append(new_vehicle)
    return vehicles


def _parse_rehitrule(j):
    rulemap = defaultdict(dict)
    data = j["rehit"]
    for k, v in data.iteritems():
        id1 = int(k)
        for k2, v2 in v.iteritems():
            id2 = int(k2)
            rulemap[id1][id2] = v2
            # rulemap[id1][id2] = True
    return rulemap


def read_inst(filepath):
    j = _read_json(filepath)
    tests = _parse_test(j)
    vehicles = _parse_vehicle(j)
    rehits = _parse_rehitrule(j)
    print "{} tests read in.".format(len(tests))
    print "{} vehicles read in.".format(len(vehicles))
    # build the cache maps
    map(lambda t: TEST_MAP.update({t.test_id: t}), tests)
    map(lambda v: VEHICLE_MAP[v.release].append(v), vehicles)
    map(lambda k: REHIT_MAP.update({k[0]: k[1]}), rehits.iteritems())

    return tests, vehicles, rehits
