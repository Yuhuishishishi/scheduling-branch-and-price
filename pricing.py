import multiprocessing
from collections import defaultdict

from gurobipy import *
import numpy as np

import tp3s_io
from colsolver import Col


class EnumPricer:
    def __init__(self, all_col_list):
        self.__col_list__ = all_col_list

    def price(self, test_dual, vehicle_dual):
        r_cost = np.array([self.__reduced_cost__(c, test_dual, vehicle_dual)
                           for c in self.__col_list__])
        min_r_cost = r_cost.min()
        min_r_idx = r_cost.argmin()
        if min_r_cost < -0.001:
            return self.__col_list__[min_r_idx], min_r_cost
        else:
            return None, None

    def __reduced_cost__(self, col, test_dual, vehicle_dual):
        cost = 50 + col.cost
        for tid in col.seq:
            cost -= test_dual[tid]
        cost -= vehicle_dual[col.vid]
        return cost


class MIPPricer:
    def __init__(self):
        self.__solver__ = None

    def price(self, test_dual, vehicle_dual):
        if not self.__solver__:
            self.__solver__ = self.__build_solver()
            self.__solver__.params.outputflag = 0

        # modify coeff in obj
        for tid in tp3s_io.TEST_MAP.keys():
            use_test = self._use_test[tid]
            use_test.obj = -test_dual[tid]

        for vrelease in tp3s_io.VEHICLE_MAP.keys():
            use_vehicle = self._use_vehicle[vrelease]
            use_vehicle.obj = -vehicle_dual[vrelease]

        self.__solver__.update()
        self.__solver__.optimize()

        if self.__solver__.status == GRB.OPTIMAL:
            # check if negative
            objval = self.__solver__.objval
            if objval < -0.001:
                col = self._parse_col()
                return col, objval
            else:
                return None, objval

        return None, None

    def __build_solver(self):
        m = Model("mip pricing")
        # variables
        self._use_test = {}
        self._use_vehicle = {}
        self._preced_test = {}
        self._tardiness = {}
        self._test_start = {}

        for tid in tp3s_io.TEST_MAP.keys():
            use_test = m.addVar(0, 1, 1, GRB.BINARY, "use test %d" % tid)
            self._use_test[tid] = use_test
            tardiness = m.addVar(0, GRB.INFINITY, 1, GRB.CONTINUOUS, "tardiness of test %d" % tid)
            self._tardiness[tid] = tardiness
            start_time = m.addVar(0, GRB.INFINITY, 0, GRB.CONTINUOUS, "start time of test %d" % tid)
            self._test_start[tid] = start_time

        for vrelease in tp3s_io.VEHICLE_MAP.keys():
            use_vehicle = m.addVar(0, 1, 1, GRB.BINARY, "use vehicle %d" % vrelease)
            self._use_vehicle[vrelease] = use_vehicle

        for tid1 in tp3s_io.TEST_MAP:
            for tid2 in tp3s_io.TEST_MAP:
                if tid1 == tid2:
                    continue

                preced = m.addVar(0, 1, 0, GRB.BINARY, "%d before %d" % (tid1, tid2))
                self._preced_test[(tid1, tid2)] = preced

        m.objcon = 50

        m.update()

        M = max([t.dur for t in tp3s_io.TEST_MAP.values()]) * 5

        # constraints
        # vehicle related constraints
        # use one vehicle
        m.addConstr(quicksum(self._use_vehicle.values()) == 1)

        # test related constraints
        for tid in tp3s_io.TEST_MAP:
            start_time = self._test_start[tid]
            tardiness = self._tardiness[tid]
            use_test = self._use_test[tid]

            t = tp3s_io.TEST_MAP[tid]
            # test release
            m.addConstr(start_time >= t.release)

            # start after vehicle release
            m.addConstr(start_time >=
                        quicksum([self._use_vehicle[vrelease] * vrelease
                                  for vrelease in tp3s_io.VEHICLE_MAP]))

            # tardiness
            m.addConstr(start_time + t.dur <= t.deadline + tardiness + M * (1 - use_test))

        # constraints related to pair of tests
        test_list_sorted = sorted(tp3s_io.TEST_MAP.values(), key=lambda x: x.test_id)
        for t1 in test_list_sorted:
            tid1 = t1.test_id
            use_test1 = self._use_test[tid1]
            start_time1 = self._test_start[tid1]
            for t2 in test_list_sorted:
                tid2 = t2.test_id
                if tid1 <= tid2:
                    break

                use_test2 = self._use_test[tid2]
                start_time2 = self._test_start[tid2]
                preced12 = self._preced_test[tid1, tid2]
                preced21 = self._preced_test[tid2, tid1]

                m.addConstr(use_test1 + use_test2 - 1 <= preced12 + preced21)
                m.addConstr(preced12 + preced21 <= 0.5 * (use_test1 + use_test2))

                m.addConstr(start_time1 + t1.dur <=
                            start_time2 + M * (1 - preced12))
                m.addConstr(start_time2 + t2.dur <=
                            start_time1 + M * (1 - preced21))

                # rehits
                if not tp3s_io.REHIT_MAP[tid1][tid2]:
                    preced12.ub = 0

                if not tp3s_io.REHIT_MAP[tid2][tid1]:
                    preced21.ub = 0

        m.update()

        return m

    def _parse_col(self):
        tests_used = []
        for tid in tp3s_io.TEST_MAP:
            use_test = self._use_test[tid]
            if use_test.x > 0.5:
                tests_used.append(tid)

        tests_used_sorted = sorted(tests_used, key=lambda t: self._test_start[t].x)
        vehicle_used = 0
        for vrelease in tp3s_io.VEHICLE_MAP:
            use_vehicle = self._use_vehicle[vrelease]
            if use_vehicle.x > 0.5:
                vehicle_used = vrelease
                break
        col = Col(tests_used_sorted, vehicle_used)
        return col


class HeuristicPricer:
    def __init__(self, tests, vehicles, rehits):
        self.__tests__ = tests
        self.__vehicles__ = vehicles
        self.__rehits__ = rehits
        self.__build_cache__()
        self._exact_pricer = None

    def __build_cache__(self):
        self.__test_map__ = {}
        self.__vehicle_map__ = {}
        for t in self.__tests__:
            self.__test_map__[t.test_id] = t
        for v in self.__vehicles__:
            self.__vehicle_map__[v.vehicle_id] = v

    def __select_best__(self, vid, seq, test_duals):
        curr_time = self.__vehicle_map__[vid].release
        for tid in seq:
            t = self.__test_map__[tid]
            if curr_time < t.release:
                curr_time = t.release
            curr_time += t.dur

        # partition the tests according to release time

        release_test_group = defaultdict(list)
        for t in self.__test_map__.values():
            release_test_group[t.release].append(t.test_id)

        for r in sorted(release_test_group.keys()):
            test_id_list = release_test_group[r]

            # compute the reduced cost increment for evey tests
            # test_id_list = sorted(self.__test_map__.keys(), key=lambda tid: self.__test_map__[tid].release)
            incr = [(tid, curr_time + max(self.__test_map__[tid].dur -
                                          self.__test_map__[tid].deadline, 0) - test_duals[tid])
                    for tid in test_id_list if self.__is_seq_comp_with_test__(seq, tid)]
            if len(incr) == 0:
                continue
            rc_incr = np.array(map(lambda x: x[-1], incr))
            # need to conquer the initiative to select later released tests
            min_rc_incr, min_idx = rc_incr.min(), rc_incr.argmin()
            if min_rc_incr < 0:
                return incr[min_idx][0]
        return None

    def price(self, test_dual, vehicle_dual):
        best_seq_on_each_vehicle = [(vid, self.__price_one_vehicle__(vid, test_dual, vehicle_dual))
                                    for vid in self.__vehicle_map__.keys()]
        # generate reduced cost
        best_col_on_each_vehicle = [Col(seq, vid) for vid, seq in best_seq_on_each_vehicle]
        reduced_cost = [self.__reduced_cost__(col, test_dual, vehicle_dual) for col in best_col_on_each_vehicle]
        reduced_cost = np.array(reduced_cost)
        if reduced_cost.min() < 0:
            return best_col_on_each_vehicle[reduced_cost.argmin()], reduced_cost.min()
        return None, reduced_cost.min()




    def price2(self, test_dual, vehicle_dual, seed_col_set):
        seq_set = [(col.vid, col.seq, test_dual) for col in seed_col_set]
        pool = multiprocessing.Pool(multiprocessing.cpu_count())
        # longest_seq = pool.map(HeuristicPricer._extend_seq_wrapper, seq_set)
        longest_seq = [(s[0], self.__extend_seq__(s[0], s[1], test_dual)) for s in seq_set]

        best_col = [Col(s[1], s[0]) for s in longest_seq]
        rc = [self.__reduced_cost__(col, test_dual, vehicle_dual) for col in best_col]
        rc = np.array(rc)
        if rc.min() < -0.001:
            return best_col[rc.argmin()], rc.min()

        # mip pricer
        if not self._exact_pricer:
            self._exact_pricer = MIPPricer(self.__tests__, self.__vehicles__, self.__rehits__)
        neg_col, rc = self._exact_pricer.price(test_dual, vehicle_dual)
        return neg_col, rc

    def __extend_seq__(self, vid, seq, test_dual):
        result = seq[:]
        while True:
            tid = self.__select_best__(vid, result, test_dual)
            if not tid:
                break
            result.append(tid)
        return result

    def __price_one_vehicle__(self, vid, test_dual, vehicle_dual):
        seq = []
        while True:
            tid = self.__select_best__(vid, seq, test_dual)
            if not tid:
                break
            seq.append(tid)
        return seq

    def __is_seq_comp_with_test__(self, seq, test):
        if test in seq:
            return False
        for tid in seq:
            if not self.__rehits__[tid][test]:
                return False
        return True

    def __reduced_cost__(self, col, test_dual, vehicle_dual):
        cost = 50 + col.cost
        for tid in col.seq:
            cost -= test_dual[tid]
        cost -= vehicle_dual[col.vid]
        return cost
