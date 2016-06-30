from Queue import PriorityQueue, LifoQueue
from collections import defaultdict

from gurobipy import *

import tp3s_io
from colsolver import ColEnumerator, Col


class BPSolver:
    BEST_INC_VAL = float("inf")
    INC_SOL = None

    def __init__(self):
        self._pending_nodes = LifoQueue()
        self._pending_nodes_best_bound = PriorityQueue()

    def add_node(self, lpbound, node):
        self._pending_nodes.put(node)
        self._pending_nodes_best_bound.put((lpbound, node))

    def solve(self):
        # enumerate the initial columns
        en = ColEnumerator()
        init_col_list = en.enum(1)

        # create the root node
        root = Node(init_col_list, [], self)
        self._pending_nodes.put(root)
        self._pending_nodes_best_bound.put((1000, root))

        iter_times = 0
        while not (self._pending_nodes.empty() or self._pending_nodes_best_bound.empty()):
            # if iter_times % 2 == 0:
            print '# Pending nodes', self._pending_nodes.qsize()
            node_to_process = self._pending_nodes.get()
            # else:
            #     _, node_to_process = self._pending_nodes_best_bound.get()

            node_to_process.process()

            iter_times += 1

        used_col = []
        for k, v in BPSolver.INC_SOL.iteritems():
            if v > 0.001:
                print k, v
                used_col.append(k)

        print 'Final obj val', BPSolver.BEST_INC_VAL
        print 'Used vehicle', len(used_col)


class Node:
    FRACTIONAL_TEST_ON_VEHICLE = 1
    FRACTIONAL_TEST_PAIR = 2
    FRACTIONAL_TEST_ORDER_PAIR_ON_VEHICLE = 3

    def __init__(self, col_set, branch_constr, bpsolver):
        self._col_set = col_set[:]  # defensive copy
        self._branch_constr_list = branch_constr[:]  # defensive copy
        self.solved = False
        self._master_solver = None
        self._pricer = None
        self._bp_solver = bpsolver

    def process(self):
        if not self.solved:
            print "Entering node"
            print "Branching constraint:"
            for c in self._branch_constr_list:
                print c.tid1, c.tid2, c.vid, c.direction
            self._solve_lp()

    def _build_master_prb(self):
        m = Model("bp sub problem")

        '''========================================
                        constraints
        ==========================================='''

        # test cover constraints
        self._test_cover_constr = {}
        for tid in tp3s_io.TEST_MAP:
            constr = m.addConstr(0, GRB.GREATER_EQUAL, 1, name="cover test %d" % tid)
            self._test_cover_constr[tid] = constr

        # vehicle capacity constraints
        self._vehicle_cap_constr = {}
        for vrelease in tp3s_io.VEHICLE_MAP:
            constr = m.addConstr(0, GRB.LESS_EQUAL, len(tp3s_io.VEHICLE_MAP[vrelease]),
                                 name="vehicle cap %d" % vrelease)
            self._vehicle_cap_constr[vrelease] = constr

        m.update()

        '''========================================
                        variables
        ==========================================='''
        self._var = {}

        # caches to speed int check
        self._cols_contain_test = defaultdict(list)
        self._cols_contain_pair_in_order = defaultdict(list)

        for col in self._col_set:
            v_constr = self._vehicle_cap_constr[col.release]
            grb_col = Column()
            grb_col.addTerms(1, v_constr)

            for tid in col.seq:
                t_constr = self._test_cover_constr[tid]
                grb_col.addTerms(1, t_constr)

            affect = self._bound_enforced_by_branch_constr(col)
            if affect == BranchConstr.FIX_TO_ONE:
                v = m.addVar(1, GRB.INFINITY, 50 + col.cost, GRB.CONTINUOUS, "use col" + str(col), grb_col)
            elif affect == BranchConstr.FIX_TO_ZERO:
                v = m.addVar(0, 0, 50 + col.cost, GRB.CONTINUOUS, "use col" + str(col), grb_col)
            else:
                v = m.addVar(0, GRB.INFINITY, 50 + col.cost, GRB.CONTINUOUS, "use col" + str(col), grb_col)

            # else doing nothing
            self._var[col] = v

            # build cache
            for i in range(0, len(col.seq)):
                tid = col.seq[i]
                self._cols_contain_test[tid].append(col)
                for j in range(0, i):
                    self._cols_contain_pair_in_order[(col.seq[j], col.seq[i])].append(col)

        m.update()
        return m

    def _bound_enforced_by_branch_constr(self, col):
        for constr in self._branch_constr_list:
            affect = constr.satisfy(col)
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
        for tid in tp3s_io.TEST_MAP:
            use_test = m.addVar(0, 1, 1, GRB.BINARY, "use test %d" % tid)
            tardiness = m.addVar(0, GRB.INFINITY, 1, GRB.CONTINUOUS, "tardiness of test %d" % tid)
            start_time = m.addVar(0, GRB.INFINITY, 0, GRB.CONTINUOUS, "start time of test %d" % tid)

            self._use_tests[tid] = use_test
            self._tardiness[tid] = tardiness
            self._start[tid] = start_time

        for vrelease in tp3s_io.VEHICLE_MAP:
            use_vehicle = m.addVar(0, 1, 1, GRB.BINARY, "use vehicle %d" % vrelease)
            self._use_vehicles[vrelease] = use_vehicle

        for tid1 in tp3s_io.TEST_MAP:
            for tid2 in tp3s_io.TEST_MAP:
                if tid1 == tid2:
                    continue

                preced = m.addVar(0, 1, 0, GRB.BINARY, "%d before %d" % (tid1, tid2))
                self._preced[(tid1, tid2)] = preced

        '''=================================
                    constraints
        ================================='''
        m.objcon = 50
        m.update()
        big_m = max([t.dur for t in tp3s_io.TEST_MAP.values()]) * 5

        # vehicle related constraints
        # use one vehicle
        m.addConstr(quicksum(self._use_vehicles.values()) == 1)

        # test related constraints
        for tid in tp3s_io.TEST_MAP:
            t = tp3s_io.TEST_MAP[tid]
            start_time = self._start[tid]
            tardiness = self._tardiness[tid]
            use_test = self._use_tests[tid]

            # test release
            m.addConstr(start_time >= t.release)

            # start after vehicle release
            m.addConstr(start_time >=
                        quicksum([self._use_vehicles[vrelease] * vrelease
                                  for vrelease in tp3s_io.VEHICLE_MAP]))

            # tardiness
            m.addConstr(start_time + t.dur <= t.deadline + tardiness + big_m * (1 - use_test))

        ordered_test_list = sorted(tp3s_io.TEST_MAP.values(), key=lambda x: x.test_id)
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
                            start_time2 + big_m * (1 - preced12))
                m.addConstr(start_time2 + t2.dur <=
                            start_time1 + big_m * (1 - preced21))

                # rehits
                if not tp3s_io.REHIT_MAP[tid1][tid2]:
                    preced12.ub = 0

                if not tp3s_io.REHIT_MAP[tid2][tid1]:
                    preced21.ub = 0

        # branching constraints related constraints
        for constr in self._branch_constr_list:
            if constr.btype == BranchConstr.TYPE_TEST_ONE_VEHICLE:
                tid = constr.tid1
                vid = constr.vid
                use_test = self._use_tests[tid]
                use_vehicle = self._use_vehicles[vid]
                if constr.direction == BranchConstr.FIX_TO_ZERO:
                    # forbid assign tid to vid
                    m.addConstr(use_test <= 1 - use_vehicle)
                elif constr.direction == BranchConstr.FIX_TO_ONE:
                    # if the vehicle is used, then test must be included
                    # if other vehicle is used, then the test must be excluded
                    m.addConstr(use_test == use_vehicle)
            elif constr.btype == BranchConstr.TYPE_TEST_PAIR_TOGETHER:
                tid1 = constr.tid1
                tid2 = constr.tid2
                use_test1 = self._use_tests[tid1]
                use_test2 = self._use_tests[tid2]
                if constr.direction == BranchConstr.FIX_TO_ZERO:
                    # test1 and test2 cannot appear together
                    m.addConstr(use_test1 + use_test2 <= 1)
                elif constr.direction == BranchConstr.FIX_TO_ONE:
                    m.addConstr(use_test1 == use_test2)
            elif constr.btype == BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE:
                tid1 = constr.tid1
                tid2 = constr.tid2
                vid = constr.vid
                use_vehicle = self._use_vehicles[vid]
                preced = self._preced[tid1, tid2]
                if constr.direction == BranchConstr.FIX_TO_ZERO:
                    # test1 cannot before test2 on vehicle vid
                    m.addConstr(preced <= 1 - use_vehicle)
                elif constr.direction == BranchConstr.FIX_TO_ONE:
                    m.addConstr(preced == use_vehicle)

        m.update()
        return m

    def _price(self, test_dual, vehicle_dual):
        # modify coeff in obj
        for tid in tp3s_io.TEST_MAP:
            use_test = self._use_tests[tid]
            use_test.obj = - test_dual[tid]
        for vrelease in tp3s_io.VEHICLE_MAP:
            use_vehicle = self._use_vehicles[vrelease]
            use_vehicle.obj = -vehicle_dual[vrelease]

        self._pricer.update()
        self._pricer.optimize()

        col = None
        obj_val = None
        if self._pricer.status == GRB.OPTIMAL:
            obj_val = self._pricer.objval
            if obj_val < -0.001:
                col = self._parse_col()

        return col, obj_val

    def _solve_lp(self):
        # build restricted master problem
        if not self._master_solver:
            self._master_solver = self._build_master_prb()
            # suppress output
            self._master_solver.params.outputflag = 0

        # build the pricing problem
        if not self._pricer:
            self._pricer = self._build_pricing_prb()
            # suppress output
            self._pricer.params.outputflag = 0

        # column generation loop
        max_iter = 1e3
        iter_times = 0
        while iter_times < max_iter:
            iter_times += 1
            self._master_solver.optimize()

            # get dual info
            test_dual = {}
            vehicle_dual = {}
            for tid, constr in self._test_cover_constr.iteritems():
                test_dual[tid] = constr.Pi
            for vid, constr in self._vehicle_cap_constr.iteritems():
                vehicle_dual[vid] = constr.Pi

            neg_col, rc = self._price(test_dual, vehicle_dual)
            if not neg_col:
                if self._master_solver.status == GRB.OPTIMAL:
                    print "master val: {}, rc: {}".format(self._master_solver.objval, rc)
                else:
                    print "master infeasible"
                break
            else:
                if self._master_solver.status == GRB.OPTIMAL:
                    print "master val: {}, rc: {}".format(self._master_solver.objval, rc)
                else:
                    print "master infeasible"

                grb_col = Column()
                grb_col.addTerms(1, self._vehicle_cap_constr[neg_col.release])
                for tid in neg_col.seq:
                    grb_col.addTerms(1, self._test_cover_constr[tid])
                v = self._master_solver.addVar(0, GRB.INFINITY, 50 + neg_col.cost, GRB.CONTINUOUS,
                                               "use col" + str(neg_col.cid), grb_col)
                self._var[neg_col] = v
                self._master_solver.update()

                self._col_set.append(neg_col)
                print "ng col", neg_col, neg_col.release

        self.solved = True

        # check the objective function value is > best integer solution value
        # if yes, no need to branch further
        lp_objval = self._master_solver.objval
        if lp_objval > BPSolver.BEST_INC_VAL:
            return

        # solve the ip version
        int_model = self._master_solver.copy()
        all_vars = int_model.getVars()
        for v in all_vars:
            v.vtype = GRB.BINARY
        int_model.update()
        int_model.optimize()
        ip_objval = int_model.objval
        print 'Int obj val', ip_objval
        if ip_objval < BPSolver.BEST_INC_VAL:
            BPSolver.BEST_INC_VAL = ip_objval
        if abs(ip_objval - lp_objval) < 0.001:
            print "OK"
            return

        # integrality check
        int_res = self._int_check()

        # branch and create subproblems
        if int_res is not None:
            node1, node2 = self._branch(int_res)
            self._bp_solver.add_node(lp_objval, node1)
            self._bp_solver.add_node(lp_objval, node2)
        else:
            # all integer, update the upper bound
            if self._master_solver.objval < BPSolver.BEST_INC_VAL:
                # record the incumbent
                used_col = self._get_used_cols()
                BPSolver.INC_SOL = used_col
                BPSolver.BEST_INC_VAL = self._master_solver.objval

    def _get_used_cols(self):
        used_col = {}
        for k, v in self._var.iteritems():
            used_col[k] = v.x
        return used_col

    def _int_check(self):
        res = self._int_check_tests_together()
        if res:
            return Node.FRACTIONAL_TEST_PAIR, res[0], res[1], None

        res = self._int_check_test_on_vehicle()
        if res:
            return Node.FRACTIONAL_TEST_ON_VEHICLE, res[0], None, res[1]
        res = self._int_check_tests_pair_order_on_vehicle()
        if res:
            return Node.FRACTIONAL_TEST_ORDER_PAIR_ON_VEHICLE, res[0], res[1], res[2]

        return None

    def _int_check_test_on_vehicle(self):
        """
        Check a test is not assigned to multiple vehicles
        :return:
        """
        tid_vid_pair = None
        dist_to_half = float("inf")
        for tid in tp3s_io.TEST_MAP:
            for vrelease in tp3s_io.VEHICLE_MAP:
                col_contain_test_on_this_vehicle = filter(lambda c: c.release == vrelease,
                                                          self._cols_contain_test[tid])
                lambda_val = sum([self._var[col].x
                                  for col in col_contain_test_on_this_vehicle])

                # find the closed to half
                if abs(lambda_val - 0.5) < dist_to_half:
                    dist_to_half = abs(lambda_val - 0.5)
                    tid_vid_pair = tid, vrelease
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
        ordered_test_list = sorted(tp3s_io.TEST_MAP.keys())
        for tid1 in ordered_test_list:
            for tid2 in ordered_test_list:
                if tid2 >= tid1:
                    break
                col_contain_both_tests = self._cols_contain_pair_in_order[tid1, tid2][:]
                col_contain_both_tests.extend(self._cols_contain_pair_in_order[tid2, tid1][:])
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
        ordered_test_list = sorted(tp3s_io.TEST_MAP.keys())
        for tid1 in ordered_test_list:
            for tid2 in ordered_test_list:
                if tid2 >= tid1:
                    break
                col_statisfy_order_t1_t2 = self._cols_contain_pair_in_order[tid1, tid2]
                col_statisfy_order_t2_t1 = self._cols_contain_pair_in_order[tid2, tid1]
                for vrelease in tp3s_io.VEHICLE_MAP:
                    lambda_val_t1_t2 = sum([self._var[col].x for col in col_statisfy_order_t1_t2
                                            if col.release == vrelease])
                    lambda_val_t2_t1 = sum([self._var[col].x for col in col_statisfy_order_t2_t1
                                            if col.release == vrelease])

                    if abs(lambda_val_t1_t2 - 0.5) < dist_to_half:
                        dist_to_half = abs(lambda_val_t1_t2 - 0.5)
                        test_pair = tid1, tid2, vrelease

                    if abs(lambda_val_t2_t1 - 0.5) < dist_to_half:
                        dist_to_half = abs(lambda_val_t2_t1 - 0.5)
                        test_pair = tid2, tid1, vrelease

        if dist_to_half > 0.4888:
            return None
        else:
            return test_pair

    def _branch(self, int_res):
        """
        Branch according to the result of integrality check
        :param int_res: result of integrality check
        :return: subproblems to add to pending list
        """
        btype = int_res[0]
        if btype == Node.FRACTIONAL_TEST_ON_VEHICLE:
            # create two branches
            constr1 = BranchConstr(int_res[1], None, int_res[-1], BranchConstr.TYPE_TEST_ONE_VEHICLE,
                                   BranchConstr.FIX_TO_ONE)
            constr2 = BranchConstr(int_res[1], None, int_res[-1], BranchConstr.TYPE_TEST_ONE_VEHICLE,
                                   BranchConstr.FIX_TO_ZERO)
        elif btype == Node.FRACTIONAL_TEST_PAIR:
            constr1 = BranchConstr(int_res[1], int_res[2], None, BranchConstr.TYPE_TEST_PAIR_TOGETHER,
                                   BranchConstr.FIX_TO_ONE)
            constr2 = BranchConstr(int_res[1], int_res[2], None, BranchConstr.TYPE_TEST_PAIR_TOGETHER,
                                   BranchConstr.FIX_TO_ZERO)
        elif btype == Node.FRACTIONAL_TEST_ORDER_PAIR_ON_VEHICLE:
            constr1 = BranchConstr(int_res[1], int_res[2], int_res[-1], BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE,
                                   BranchConstr.FIX_TO_ONE)
            constr2 = BranchConstr(int_res[1], int_res[2], int_res[-1], BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE,
                                   BranchConstr.FIX_TO_ZERO)
        else:
            print "Integrality result btype error"
            constr1 = None
            constr2 = None

        # two branches created

        constr_list1 = self._branch_constr_list[:]
        constr_list2 = self._branch_constr_list[:]
        constr_list1.append(constr1)
        constr_list2.append(constr2)
        node1 = Node(self._col_set, constr_list1, self._bp_solver)
        node2 = Node(self._col_set, constr_list2, self._bp_solver)

        return node1, node2

    def _parse_col(self):
        tests_used = []
        for tid in tp3s_io.TEST_MAP:
            use_test = self._use_tests[tid]
            if use_test.x > 0.5:
                tests_used.append(tid)

        tests_used_sorted = sorted(tests_used, key=lambda tid: self._start[tid].x)
        vehicle_used = 0
        for vrelease in tp3s_io.VEHICLE_MAP:
            use_vehicle = self._use_vehicles[vrelease]
            if use_vehicle.x > 0.5:
                vehicle_used = vrelease
                break
        col = Col(tests_used_sorted, vehicle_used)
        return col


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

    def __init__(self, tid1, tid2, vid, btype, direction):
        """
        constructor of a branch constraint
        :param tid1: id of first test
        :param tid2: id of second test
        :param vid:  id of vehicle
        :param btype: btype of branching constraint (TEST_ON_VEHICLE, TEST_PAIR_TOGETHER, TEST_PAIR_ORDER_ON_VEHICLE)
        :param direction: branching firection (FIX_TO_ZERO, FIX_TO_ONE)
        :return: a branching constraint
        """
        self.tid1 = tid1
        self.tid2 = tid2
        self.vid = vid
        self.btype = btype
        self.direction = direction

    def satisfy(self, col):
        """
        If a column satisfies such branching constraint.
        return true if satisfied, false otherwise.
        In case of not satisfied, such column needs to be fixed to zero
        :param col:
        :return: true if satisfied, false if not satisfied
        """
        if self.direction == BranchConstr.FIX_TO_ZERO:
            # if a column satisfies the criteria (contains relevant tests, vehicles), it will be fixed to zero
            if self.btype == BranchConstr.TYPE_TEST_ONE_VEHICLE:
                if self.tid1 in col.seq and col.vid == self.vid:
                    return BranchConstr.FIX_TO_ZERO
            elif self.btype == BranchConstr.TYPE_TEST_PAIR_TOGETHER:
                if self.tid1 in col.seq \
                        and self.tid2 in col.seq:
                    return BranchConstr.FIX_TO_ZERO
            elif self.btype == BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE:
                if self.tid1 in col.seq \
                        and self.tid2 in col.seq \
                        and col.seq.index(self.tid1) < col.seq.index(self.tid2) \
                        and col.vid == self.vid:
                    return BranchConstr.FIX_TO_ZERO
            return BranchConstr.NO_IMPACT
        elif self.direction == BranchConstr.FIX_TO_ONE:
            # if a column satisfies partially the criteria (contains relevant tests, vehicles), it will be fixed to zero
            if self.btype == BranchConstr.TYPE_TEST_ONE_VEHICLE:
                if self.tid1 in col.seq \
                        and col.vid != self.vid:  # contains the test, but assign the test to other vehicles
                    return BranchConstr.FIX_TO_ZERO
            elif self.btype == BranchConstr.TYPE_TEST_PAIR_TOGETHER:
                if self.tid1 in col.seq and self.tid2 not in col.seq:
                    # if contains exactly one of two tests
                    return BranchConstr.FIX_TO_ZERO
                if self.tid2 in col.seq and self.tid1 not in col.seq:
                    return BranchConstr.FIX_TO_ZERO
            elif self.btype == BranchConstr.TYPE_TEST_PAIR_ORDER_ON_VEHICLE:
                if self.tid1 in col.seq and self.tid2 not in col.seq:
                    # if contains exactly one of two tests
                    return BranchConstr.FIX_TO_ZERO
                if self.tid2 in col.seq and self.tid1 not in col.seq:
                    return BranchConstr.FIX_TO_ZERO
                if self.tid1 in col.seq \
                        and self.tid2 in col.seq:
                    if col.seq.index(self.tid1) > col.seq.index(self.tid2):  # t1 after t2
                        return BranchConstr.FIX_TO_ZERO
            return BranchConstr.NO_IMPACT
        else:
            print "Unknown branching constraint btype"
            return None
