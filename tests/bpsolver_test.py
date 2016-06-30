import unittest

import tp3s_io
from bpsolver import BPSolver

filepath = r"..\data\157.tp3s"


class BPSolverTestCase(unittest.TestCase):
    def test_bpsolver_initialization(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        print rehits

        solver = BPSolver()
        solver.solve()



if __name__ == '__main__':
    unittest.main()
