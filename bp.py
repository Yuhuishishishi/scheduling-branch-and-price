from collections import defaultdict

from gurobipy import *

TEST_MAP = {}
VEHICLE_MAP = {}
REHIT_MAP = {}


class Node:
    LB = 0
    UB = float("inf")
    NID = 0

    def __init__(self, col_set, branch_constr):
        self._col_set = col_set[:]
        self._branch_constr_list = branch_constr[:]
        self.solved = False
        self._master_solver = None
        self._pricer = None

    def _build_master_prb(self):
        m = Model("bp sub problem {}".format(Node.NID))
        Node.NID += 1

        '''========================================
                        constraints
        ==========================================='''

        # test cover constraints
        self._test_cover_constr = {}
        for tid in TEST_MAP:
            constr = m.addConstr(0, GRB.GREATER_EQUAL, 1, name="cover test %d" % tid)
            self._test_cover_constr[tid] = constr

        # vehicle capacity constraints
        self._vehicle_cap_constr = {}
        for vid in VEHICLE_MAP:
            constr = m.addConstr(0, GRB.LESS_EQUAL, 1, name="vehicle cap %d" % vid)
            self._vehicle_cap_constr[vid] = constr

        m.update()

        '''========================================
                        variables
        ==========================================='''
        self._var = {}

        self._cols_contain_test_map = defaultdict(list)
        for col in self._col_set:
            v_constr = self._vehicle_cap_constr[col.vid]
            grb_col = Column()
            grb_col.addTerms(1, v_constr)

            for tid in col.seq:
                t_constr = self._test_cover_constr[tid]
                grb_col.addTerms(1, t_constr)
                self._cols_contain_test_map[tid].append(col)

            v = m.addVar(0, 1, 50 + col.cost, GRB.BINARY, "use col" + str(col), grb_col)
            # check branching constraints
            affect = self._bound_enforced_by_branch_constr(col)
            if affect == BranchConstr.FIX_TO_ONE:
                v.lb = 1
            elif affect == BranchConstr.FIX_TO_ZERO:
                v.ub = 0
            # else doing nothing
            self._var[col] = v

        m.update()
        return m

    def _bound_enforced_by_branch_constr(self, col):
        for constr in self._branch_constr_list:
            affect = constr.enforce(col)
            if affect == BranchConstr.NO_IMPACT:
                continue
            else:
                return affect

        return BranchConstr.NO_IMPACT

    def _build_pricing_prb(self):
        m = Model("pricing")
        # variables
        self._use_tests = {}
        self._use_vehicles = {}
        self._preced = {}
        self._tardiness = {}
        self._start = {}

        '''=================================
                    variables
        ================================='''
        for tid in TEST_MAP:
            use_test = m.addVar(0, 1, 1, GRB.BINARY, "use test %d" % tid)
            tardiness = m.addVar(0, GRB.INFINITY, 1, GRB.CONTINUOUS, "tardiness of test %d" % tid)
            start_time = m.addVar(0, GRB.INFINITY, 0, GRB.CONTINUOUS, "start time of test %d" % tid)

            self._use_tests[tid] = use_test
            self._tardiness[tid] = tardiness
            self._start[tid] = start_time

        for vid in VEHICLE_MAP:
            use_vehicle = m.addVar(0, 1, 1, GRB.BINARY, "use vehicle %d" % vid)
            self._use_vehicles[vid] = use_vehicle

        for tid1 in TEST_MAP:
            for tid2 in TEST_MAP:
                if tid1 == tid2:
                    continue

                preced = m.addVar(0, 1, 0, GRB.BINARY, "%d before %d" % (tid1, tid2))
                self._preced[(tid1, tid2)] = preced

        '''=================================
                    constraints
        ================================='''
        m.objcon = 50
        m.update()
        M = max([t.dur for t in TEST_MAP]) * 5

        # vehicle related constraints
        # use one vehicle
        m.addConstr(quicksum(self._use_vehicles.values()) == 1)

        # test related constraints
        for tid in TEST_MAP:
            t = TEST_MAP[tid]
            start_time = self._start[tid]
            tardiness = self._tardiness[tid]
            use_test = self._use_tests[tid]

            # test release
            m.addConstr(start_time >= t.release)

            # start after vehicle release
            m.addConstr(start_time >=
                        quicksum([self._use_vehicles[v.vehicle_id] * v.release
                                  for v in VEHICLE_MAP.values()]))

            # tardiness
            m.addConstr(start_time + t.dur <= t.deadline + tardiness + M * (1 - use_test))

        ordered_test_list = sorted(TEST_MAP.values(), key=lambda t: t.release)
        for t1 in ordered_test_list:
            tid1 = t1.test_id
            use_test1 = self._use_tests[tid1]
            start_time1 = self._start[tid1]
            for t2 in ordered_test_list:
                tid2 = t2.test_id
                if tid1 <= tid2:
                    break

                use_test2 = self._use_tests[tid2]
                start_time2 = self._start[tid2]
                preced12 = self._preced[tid1, tid2]
                preced21 = self._preced[tid2, tid1]

                m.addConstr(use_test1 + use_test2 - 1 <= preced12 + preced21)
                m.addConstr(preced12 + preced21 <= 0.5 * (use_test1 + use_test2))

                m.addConstr(start_time1 + t1.dur <=
                            start_time2 + M * (1 - preced12))
                m.addConstr(start_time2 + t2.dur <=
                            start_time1 + M * (1 - preced21))

                # rehits
                if not REHIT_MAP[tid1][tid2]:
                    preced12.ub = 0

                if not REHIT_MAP[tid2][tid1]:
                    preced21.ub = 0

        # branching constraints related constraints
        for constr in self._branch_constr_list:
            if constr._type == BranchConstr.TYPE_TEST_ONE_VEHICLE:
                tid = constr._tid1
                vid = constr._vid
                use_test = self._use_tests[tid]
                use_vehicle = self._use_vehicles[vid]
                if constr._direction == BranchConstr.FIX_TO_ZERO:
                    # forbid assign tid to vid
                    m.addConstr(use_test <= 1 - use_vehicle)
                elif constr._direction == BranchConstr.FIX_TO_ONE:
                    m.addConstr(use_test >= use_vehicle)
            elif constr._type == BranchConstr.TYPE_TEST_PAIR_TOGETHER:
                tid1 = constr._tid1
                tid2 = constr._tid2
                use_test1 = self._use_tests[tid1]
                use_test2 = self._use_tests[tid2]
                if constr._direction == BranchConstr.FIX_TO_ZERO:
                    # test1 and test2 cannot appear together
                    m.addConstr(use_test1 + use_test2 <= 1)
                elif constr._direction == BranchConstr.FIX_TO_ZERO:
                    m.addConstr(use_test1 == use_test2)
            elif constr._type == BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE:
                tid1 = constr._tid1
                tid2 = constr._tid2
                vid = constr._vid
                use_vehicle = self._use_vehicles[vid]
                preced = self._preced[tid1, tid2]
                if constr._direction == BranchConstr.FIX_TO_ZERO:
                    # test1 cannot before test2 on vehicle vid
                    m.addConstr(preced <= 1 - use_vehicle)
                elif constr._direction == BranchConstr.FIX_TO_ONE:
                    m.addConstr(preced >= use_vehicle)

        m.update()
        return m

    def _solve_lp(self):
        # build restricted master problem

        # build the pricing problem

        # column generation loop

        # integrality check

        # branch and create subproblems
        pass

    def _int_check(self):
        res = self._int_check_test_on_vehicle()
        if res:
            return res
        res = self._int_check_tests_together()
        if res:
            return res
        res = self._int_check_tests_pair_order_on_vehicle()
        if res:
            return res

    def _int_check_test_on_vehicle(self):
        """
        Check a test is not assigned to multiple vehicles
        :return:
        """
        tid_vid_pair = None
        dist_to_half = float("inf")
        for tid in TEST_MAP:
            for vid in VEHICLE_MAP:
                col_contain_test_on_this_vehicle = filter(lambda c: c.vid == vid,
                                                          self._cols_contain_test_map[tid])
                lambda_val = sum([self._var[col].x
                                  for col in col_contain_test_on_this_vehicle])
                # find the closed to half
                if abs(lambda_val - 0.5) < dist_to_half:
                    dist_to_half = abs(lambda_val - 0.5)
                    tid_vid_pair = tid, vid
        # check the distance
        if dist_to_half > 0.4888:
            return None
        else:
            return tid_vid_pair

    def _int_check_tests_together(self):
        """
        Check a pair of tests are together
        :return:
        """
        dist_to_half = float("inf")
        test_pair = None
        ordered_test_list = sorted(TEST_MAP.keys())
        for tid1 in ordered_test_list:
            for tid2 in ordered_test_list:
                if tid2 >= tid1:
                    break
                col_contain_both_tests = filter(lambda c: c in self._cols_contain_test_map[tid2],
                                                self._cols_contain_test_map[tid1])
                lambda_val = sum([self._var[col].x for col in col_contain_both_tests])
                if abs(lambda_val - 0.5) < dist_to_half:
                    dist_to_half = abs(lambda_val - 0.5)
                    test_pair = tid1, tid2
        # check the distance
        if dist_to_half > 0.4888:
            return None
        else:
            return test_pair

    def _int_check_tests_pair_order_on_vehicle(self):
        """
        Check a pair of tests arranged in certain order
        :return:
        """
        dist_to_half = float("inf")
        test_pair = None
        ordered_test_list = sorted(TEST_MAP.keys())
        for tid1 in ordered_test_list:
            for tid2 in ordered_test_list:
                if tid2 >= tid1:
                    break
                col_contain_both_tests = filter(lambda c: c in self._cols_contain_test_map[tid2],
                                                self._cols_contain_test_map[tid1])
                col_statisfy_order_t1_t2 = filter(lambda c: c.seq.index(tid1) < c.seq.index(tid2),
                                                  col_contain_both_tests)
                col_statisfy_order_t2_t1 = filter(lambda c: c.seq.index(tid1) > c.seq.index(tid2),
                                                  col_contain_both_tests)
                for vid in VEHICLE_MAP:
                    lambda_val_t1_t2 = sum([self._var[col] for col in col_statisfy_order_t1_t2
                                            if col.vid == vid])
                    lambda_val_t2_t1 = sum([self._var[col] for col in col_statisfy_order_t2_t1
                                            if col.vid == vid])

                    if abs(lambda_val_t1_t2 - 0.5) < dist_to_half:
                        dist_to_half = abs(lambda_val_t1_t2)
                        test_pair = tid1, tid2, vid

                    if abs(lambda_val_t2_t1 - 0.5) < dist_to_half:
                        dist_to_half = abs(lambda_val_t2_t1)
                        test_pair = tid2, tid1, vid

        if dist_to_half > 0.4888:
            return None
        else:
            return test_pair

    def _branch(self):
        # do the integrality check

        pass


class BranchConstr:
    """
    TEST_ONE_VEHICLE: if one test needs to be assigned to one vehicle
    TEST_PAIR_TOGETHER: if two tests needs to be assigned together
    TEST_PAIR_ORDER_ON_VEHICLE: if two tests need to be assigned to a vehicle and arranged in a particular order
    """
    TYPE_TEST_ONE_VEHICLE = 1
    TYPE_TEST_PAIR_TOGETHER = 2
    TYPE_TEST_PAIR_ORDER_ON_VEHICLE = 3

    FIX_TO_ZERO = 0
    FIX_TO_ONE = 1
    NO_IMPACT = 2

    def __init__(self, tid1, tid2, vid, type, direction):
        """
        constructor of a branch constraint
        :param tid1: id of first test
        :param tid2: id of second test
        :param vid:  id of vehicle
        :param type: type of branching constraint (TEST_ON_VEHICLE, TEST_PAIR_TOGETHER, TEST_PAIR_ORDER_ON_VEHICLE)
        :param direction: branching firection (FIX_TO_ZERO, FIX_TO_ONE)
        :return: a branching constraint
        """
        self._tid1 = tid1
        self._tid2 = tid2
        self._vid = vid
        self._type = type
        self._direction = direction

    def enforce(self, col):
        """
        whether to enforce a branching constraint on a column; return true if such column needs to be fixed
        to zero or one
        :param col: a column
        :return: FIX_TO_ZERO; FIX_TO_ONE; NO_IMPACT
        """
        if self._type == BranchConstr.TEST_ONE_VEHICLE:
            # assume tid2 is none
            if self.tid1 in col.seq and self._vid == col.vid:
                return self._direction
            else:
                return BranchConstr.NO_IMPACT
        elif self._type == BranchConstr.TYPE_TEST_PAIR_TOGETHER:
            if self._tid1 in col.seq and self._tid2 in col.seq:
                return self._direction
            else:
                return BranchConstr.NO_IMPACT
        elif self._type == BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE:
            if self._tid1 in col.seq and self._tid2 in col.seq and self._vid == col.vid:
                if col.seq.index(self._tid1) < col.seq.index(self._tid2):
                    return self._direction
                else:
                    return BranchConstr.NO_IMPACT
            else:
                return BranchConstr.NO_IMPACT
        else:
            print "Branching constraint undefined"
            return None
