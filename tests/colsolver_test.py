import unittest
import tp3s_io
from colsolver import ColSolver, ColEnumerator


filepath = r"C:\Users\yuhuishi\Desktop\scheduling-branch-and-price\data\157.tp3s"

class ColSolverTestCase(unittest.TestCase):
    def testcache(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        self.assertSequenceEqual(sorted(solver.TEST_MAP.keys()),
                                 sorted([t.test_id for t in tests]))

    def testcachevehicle(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        self.assertSequenceEqual(sorted(solver.VEHICLE_MAP.keys()),
                                 sorted([v.vehicle_id for v in vehicles]))

    def testenumerator(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)
        enumerator = ColEnumerator()
        collist = enumerator.enum()
        seq = collist[-1]
        print seq, seq.cost


    def testgrbsolver(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        solver.solve_full_enum()

    def testgrbsolvercolgen(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        solver.solve_col_gen()