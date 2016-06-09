from gurobipy import *
import numpy as np

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
    def __init__(self, tests, vehicles, rehits):
        self.__tests__ = tests
        self.__vehicles__ = vehicles
        self.__rehits__ = rehits
        self.__solver__ = None

    def price(self, test_dual, vehicle_dual):
        if not self.__solver__:
            self.__solver__ = self.__build_solver()
            self.__solver__.params.outputflag = 0

        # modify coeff in obj
        for t in self.__tests__:
            tid = t.test_id
            use_test = self.__use_test__[tid]
            use_test.obj = -test_dual[tid]

        for v in self.__vehicles__:
            vid = v.vehicle_id
            use_vehicle = self.__use_vehicle__[vid]
            use_vehicle.obj = -vehicle_dual[vid]

        self.__solver__.update()
        self.__solver__.optimize()

        if self.__solver__.status == GRB.OPTIMAL:
            # check if negative
            objval = self.__solver__.objval
            if objval < -0.001:
                col = self.__parse_col__()
                return col, objval
            else:
                return None, None

        return None, None

    def __build_solver(self):
        m = Model("mip pricing")
        # variables
        self.__use_test__ = {}
        self.__use_vehicle__ = {}
        self.__preced_test__ = {}
        self.__tardiness__ = {}
        self.__test_start__ = {}

        for t in self.__tests__:
            tid = t.test_id
            use_test = m.addVar(0, 1, 1, GRB.BINARY, "use test %d" % tid)
            self.__use_test__[tid] = use_test
            tardiness = m.addVar(0, GRB.INFINITY, 1, GRB.CONTINUOUS, "tardiness of test %d" % tid)
            self.__tardiness__[tid] = tardiness
            start_time = m.addVar(0, GRB.INFINITY, 0, GRB.CONTINUOUS, "start time of test %d" % tid)
            self.__test_start__[tid] = start_time

        for v in self.__vehicles__:
            vid = v.vehicle_id
            use_vehicle = m.addVar(0, 1, 1, GRB.BINARY, "use vehicle %d" % vid)
            self.__use_vehicle__[vid] = use_vehicle

        for t1 in self.__tests__:
            tid1 = t1.test_id
            for t2 in self.__tests__:
                tid2 = t2.test_id
                if tid1 == tid2:
                    continue

                preced = m.addVar(0, 1, 0, GRB.BINARY, "%d before %d" % (tid1, tid2))
                self.__preced_test__[(tid1, tid2)] = preced

        m.objcon = 50

        m.update()

        M = max([t.dur for t in self.__tests__]) * 5

        # constraints
        # vehicle related constraints
        # use one vehicle
        m.addConstr(quicksum(self.__use_vehicle__.values()) == 1)

        # test related constraints
        for t in self.__tests__:
            tid = t.test_id
            start_time = self.__test_start__[tid]
            tardiness = self.__tardiness__[tid]
            use_test = self.__use_test__[tid]

            # test release
            m.addConstr(start_time >= t.release)

            # start after vehicle release
            m.addConstr(start_time >=
                        quicksum([self.__use_vehicle__[v.vehicle_id] * v.release
                                  for v in self.__vehicles__]))

            # tardiness
            m.addConstr(start_time + t.dur <= t.deadline + tardiness + M * (1 - use_test))

        # constraints related to pair of tests
        for t1 in self.__tests__:
            tid1 = t1.test_id
            use_test1 = self.__use_test__[tid1]
            start_time1 = self.__test_start__[tid1]
            for t2 in self.__tests__:
                tid2 = t2.test_id
                if tid1 <= tid2:
                    break

                use_test2 = self.__use_test__[tid2]
                start_time2 = self.__test_start__[tid2]
                preced12 = self.__preced_test__[tid1, tid2]
                preced21 = self.__preced_test__[tid2, tid1]

                m.addConstr(use_test1 + use_test2 - 1 <= preced12 + preced21)
                m.addConstr(preced12 + preced21 <= 0.5 * (use_test1 + use_test2))

                m.addConstr(start_time1 + t1.dur <=
                            start_time2 + M * (1 - preced12))
                m.addConstr(start_time2 + t2.dur <=
                            start_time1 + M * (1 - preced21))

                # rehits
                if not self.__rehits__[tid1][tid2]:
                    preced12.ub = 0

                if not self.__rehits__[tid2][tid1]:
                    preced21.ub = 0

        m.update()

        return m

    def __parse_col__(self):
        tests_used = []
        for t in self.__tests__:
            tid = t.test_id
            use_test = self.__use_test__[tid]
            if use_test.x > 0.5:
                tests_used.append(tid)

        tests_used_sorted = sorted(tests_used, key=lambda t: self.__test_start__[t].x)
        vehicle_used = 0
        for v in self.__vehicles__:
            vid = v.vehicle_id
            use_vehicle = self.__use_vehicle__[vid]
            if use_vehicle.x > 0.5:
                vehicle_used = vid
                break
        col = Col(tests_used_sorted, vehicle_used)
        return col


class HeuristicPricer:
    def __init__(self, tests, vehicles, rehits):
        self.__tests__ = tests
        self.__vehicles__ = vehicles
        self.__rehits__ = rehits

    def __select_best__(self, vehicle, seq, test_duals):
        curr_time = vehicle.release + sum([t.dur for t in seq])

        incr = [curr_time+t.dur-t.deadline - test_duals[t.test_id]
                for t in self.__tests__]


    def __is_seq_comp_with_test__(self,seq,test):
        pass