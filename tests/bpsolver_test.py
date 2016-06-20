import unittest

import tp3s_io
from bp import BPSolver
from colsolver import ColSolver

filepath = r"C:\Users\yuhuishi\Desktop\scheduling-branch-and-price\data\157.tp3s"


class BPSolverTestCase(unittest.TestCase):
    def test_bpsolver_initialization(self):
        tests, vehicles, rehits = tp3s_io.read_inst(filepath)
        print rehits

        colsolver = ColSolver(tests, vehicles, rehits)

        solver = BPSolver(tests,vehicles,rehits)
        solver.solve()



if __name__ == '__main__':
    unittest.main()
