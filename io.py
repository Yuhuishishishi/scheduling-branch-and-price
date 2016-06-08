import json
from collections import namedtuple, defaultdict

TestRequest = namedtuple("TestRequest", ["test_id", "release", "deadline", "dur"])
Vehicle = namedtuple("Vehicle", ["vehicle_id", "release"])


def __read_json__(filepath):
    with open(filepath) as f:
        data = f.read()
    j = json.loads(data)
    return j


def __parse_test__(j):
    tests = []
    data = j["tests"]
    for t in data:
        dur = t["dur"]
        r = t["release"]
        d = t["deadline"]
        i = t["test_id"]
        new_test = TestRequest(i, r, d, dur)
        tests.append(new_test)
    return tests


def __parse_vehicle__(j):
    vehicles = []
    data = j["vehicles"]
    for v in data:
        i = v["vehicle_id"]
        r = v["release"]
        new_vehicle = Vehicle(i, r)
        vehicles.append(new_vehicle)
    return vehicles


def __parse_rehitrule__(j):
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
    j = __read_json__(filepath)
    tests = __parse_test__(j)
    vehicles = __parse_vehicle__(j)
    rehits = __parse_rehitrule__(j)
    print "{} tests read in.".format(len(tests))
    print "{} vehicles read in.".format(len(vehicles))
    return tests,vehicles,rehits
