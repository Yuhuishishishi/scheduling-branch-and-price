from uuid import uuid1

from gurobipy import *

import tp3s_io


class ColSolver:
    def __init__(self):
        pass

    def _build_full_enum_model(self, startlvl=100):
        # enumerate all columns
        enumerator = ColEnumerator()
        all_cols = enumerator.enum(maxlvl=startlvl)

        m = Model("full enum model")
        # build constraints first
        # cover tests
        self.test_cover_constr = {}
        for tid in tp3s_io.TEST_MAP.keys():
            constr = m.addConstr(0, GRB.GREATER_EQUAL, 1, name="cover test %d" % tid)
            self.test_cover_constr[tid] = constr

        # vehicle capacity constr
        self.vehicle_cap_constr = {}
        for vrelease in tp3s_io.VEHICLE_MAP.keys():
            constr = m.addConstr(0, GRB.LESS_EQUAL, len(tp3s_io.VEHICLE_MAP[vrelease]),
                                 name="vehicle cap %d" % vrelease)
            self.vehicle_cap_constr[vrelease] = constr

        m.update()

        self.var = {}
        # add variables
        for col in all_cols:
            v_constr = self.vehicle_cap_constr[col.release]
            grb_col = Column()
            grb_col.addTerms(1, v_constr)

            for tid in col.seq:
                t_constr = self.test_cover_constr[tid]
                grb_col.addTerms(1, t_constr)

            v = m.addVar(0, 1, 50 + col.cost, GRB.BINARY, "use col" + str(col), grb_col)
            self.var[col] = v

        m.update()
        return m

    def _parse_sol(self):
        vehicle_usage = 0
        used_col = []
        for c, v in self.var.iteritems():
            if v.X > 0.5:
                used_col.append(c)
                vehicle_usage += 1
        print "Total vehicles: ", vehicle_usage
        return used_col

    def solve_full_enum(self):
        m = self._build_full_enum_model()
        m.optimize()

        if m.status == GRB.OPTIMAL:
            _ = self._parse_sol()
        else:
            print 'model status abnormal', m.status

    def solve_col_gen(self):
        m = self._build_full_enum_model(startlvl=0)
        m.params.outputflag = 0
        for v in self.var.values():
            v.VType = GRB.CONTINUOUS
            v.UB = GRB.INFINITY
        m.update()

        max_iter = 1e5
        iter_times = 0

        # all_col_list = ColEnumerator().enum()
        seed_col_list = ColEnumerator().enum(maxlvl=0)

        # from pricing import HeuristicPricer
        from pricing import MIPPricer

        # pricer2 = EnumPricer(all_col_list)

        pricer = MIPPricer()
        # pricer = HeuristicPricer(self.__tests__, self.__vehicles__, self.__rehits__)
        while iter_times < max_iter:
            m.optimize()
            # get dual info
            test_dual = {}
            vehicle_dual = {}
            for tid, constr in self.test_cover_constr.iteritems():
                test_dual[tid] = constr.Pi
            for vrelease, constr in self.vehicle_cap_constr.iteritems():
                vehicle_dual[vrelease] = constr.Pi
            neg_rc_col, rc = pricer.price(test_dual, vehicle_dual)
            # neg_rc_col, rc = pricer.price2(test_dual, vehicle_dual, seed_col_list)

            if neg_rc_col is None:
                if m.status == GRB.OPTIMAL:
                    print "master val:{}, most neg rc: {}".format(m.ObjVal, "positive")
                else:
                    print m.status
                break
            else:
                # add variable
                if m.status == GRB.OPTIMAL:
                    print "master val:{}, most neg rc: {}".format(m.ObjVal, rc)
                else:
                    print m.status

                grb_col = Column()
                grb_col.addTerms(1, self.vehicle_cap_constr[neg_rc_col.release])
                for tid in neg_rc_col.seq:
                    grb_col.addTerms(1, self.test_cover_constr[tid])
                v = m.addVar(0, GRB.INFINITY, 50 + neg_rc_col.cost, GRB.CONTINUOUS,
                             "use col" + str(neg_rc_col.cid), grb_col)
                self.var[neg_rc_col] = v
                m.update()

                seed_col_list.append(neg_rc_col)


class Col:
    def __init__(self, seq, release):
        self.seq = []
        self.seq.extend(seq)
        # self.vid = vid
        self.release = release
        self.cost = self._compute_col_cost()
        self.cid = uuid1()

    def _compute_col_cost(self):
        totalcost = 0
        start = self.release
        for tid in self.seq:
            test = tp3s_io.TEST_MAP[tid]
            if start < test.release:
                start = test.release
            start += test.dur
            if start > test.deadline:
                cost = start - test.deadline
                totalcost += cost
        return totalcost

    def comp_with(self, tid):
        if tid in self.seq:
            return False

        for t in self.seq:
            if not tp3s_io.REHIT_MAP[t][tid]:
                return False

        return True

    def __repr__(self):
        return str(self.seq)


class ColEnumerator:

    def __init__(self):
        pass

    @staticmethod
    def _enum_col(collist):
        result = []
        for c in collist:
            for tid in tp3s_io.TEST_MAP.keys():
                if c.comp_with(tid):
                    s = []
                    s.extend(c.seq)
                    s.append(tid)
                    new_col = Col(s, c.release)
                    result.append(new_col)
        return result

    def enum(self, maxlvl=100):
        # initial set
        result = []
        curr_lvl = []
        for tid in tp3s_io.TEST_MAP.keys():
            for vrelease in tp3s_io.VEHICLE_MAP.keys():
                new_col = Col([tid], vrelease)
                curr_lvl.append(new_col)

        print "{} initial columns".format(len(curr_lvl))
        result.extend(curr_lvl)
        lvl = 0
        while lvl < maxlvl:
            lvl += 1
            nxt_lvl = self._enum_col(curr_lvl)
            print "lvl: {}, {} columns".format(lvl, len(nxt_lvl))
            if len(nxt_lvl) == 0:
                break
            result.extend(nxt_lvl)
            curr_lvl = []
            curr_lvl.extend(nxt_lvl)

        print "Total columns: {}".format(len(result))
        return result
