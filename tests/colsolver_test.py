import unittest
import tp3s_io
from colsolver import ColSolver, ColEnumerator


class ColSolverTestCase(unittest.TestCase):
    def testcache(self):
        filepath = r"C:\Users\yuhui\Desktop\TP3S\instance\157.tp3s"
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        self.assertSequenceEqual(sorted(solver.TEST_MAP.keys()),
                                 sorted([t.test_id for t in tests]))

    def testcachevehicle(self):
        filepath = r"C:\Users\yuhui\Desktop\TP3S\instance\157.tp3s"
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        self.assertSequenceEqual(sorted(solver.VEHICLE_MAP.keys()),
                                 sorted([v.vehicle_id for v in vehicles]))

    def testenumerator(self):
        filepath = r"C:\Users\yuhui\Desktop\TP3S\instance\157.tp3s"
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)
        enumerator = ColEnumerator()
        collist = enumerator.enum()
        seq = collist[-1]
        print seq, seq.cost


    def testgrbsolver(self):
        filepath = r"C:\Users\yuhui\Desktop\TP3S\instance\157.tp3s"
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        solver.solve_full_enum()

    def testgrbsolvercolgen(self):
        filepath = r"C:\Users\yuhui\Desktop\TP3S\instance\157.tp3s"
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        solver = ColSolver(tests, vehicles, rehits)

        solver.solve_col_gen()