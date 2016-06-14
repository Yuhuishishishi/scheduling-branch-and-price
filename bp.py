class Node:
    LB = 0
    UB = float("inf")

    def __init__(self, col_set, branch_constr):
        self._col_set = col_set[:]
        self._branch_constr = branch_constr[:]
        self.solved = False

    def _build_master_prb(self):
        pass

    def _build_pricing_prb(self):
        pass

    def _solve_lp(self):
        # build restricted master problem

        # build the pricing problem

        # column generation loop

        # integrality check

        # branch and create subproblems
        pass

    def _int_check(self):
        pass

    def _branch(self):
        pass


class BranchConstr:
    TYPE_TEST_ONE_VEHICLE = 1
    TYPE_TEST_PAIR_TOGETHER = 2
    TYPE_TEST_PAIR_ORDER_ON_VEHICLE = 3

    FIX_TO_ZERO = 0
    FIX_TO_ONE = 1
    NO_IMPACT = 2

    def __init__(self, tid1, tid2, vid, type, direction):
        self._tid1 = tid1
        self._tid2 = tid2
        self._vid = vid
        self._type = type
        self._direction = direction

    def enforce(self, col):
        """
        wheather to enforce a branching constraint on column; return true if such column needs to be fixed
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



