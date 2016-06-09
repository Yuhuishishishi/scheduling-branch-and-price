import tp3s_io
from colsolver import ColSolver


def main():
    filepath = r"C:\Users\yuhui\Desktop\TP3S\instance\157.tp3s"
    tests, vehicles, rehits = tp3s_io.read_inst(filepath)
    solver = ColSolver(tests, vehicles, rehits)

    solver.solve_col_gen()


if __name__ == '__main__':
    main()
