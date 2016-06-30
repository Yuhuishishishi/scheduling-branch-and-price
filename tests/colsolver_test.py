import unittest
import tp3s_io
from colsolver import ColSolver, ColEnumerator

filepath = r"../data/158 - Copy.tp3s"


class ColSolverTestCase(unittest.TestCase):
    def testcache(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)

        self.assertSequenceEqual(sorted(tp3s_io.TEST_MAP.keys()),
                                 sorted([t.test_id for t in tests]))

    def testcachevehicle(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)

        self.assertSequenceEqual(sorted(tp3s_io.VEHICLE_MAP.keys()),
                                 sorted(set([v.release for v in vehicles])))

    def testenumerator(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        enumerator = ColEnumerator()
        collist = enumerator.enum()
        seq = collist[-1]
        print seq, seq.cost

    def testgrbsolver(self):
        tp3s_io.read_inst(filepath)
        solver = ColSolver()

        solver.solve_full_enum()

    def testgrbsolvercolgen(self):
        tp3s_io.read_inst(filepath)
        solver = ColSolver()

        solver.solve_col_gen()
