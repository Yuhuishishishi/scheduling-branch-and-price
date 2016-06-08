from gurobipy import *
import numpy as np


class EnumPricer:
    def __init__(self, all_col_list):
        self.__col_list__ = all_col_list

    def price(self, test_dual, vehicle_dual):
        r_cost = np.array([self.__reduced_cost__(c, test_dual, vehicle_dual)
                           for c in self.__col_list__])
        min_r_cost = r_cost.min()
        min_r_idx = r_cost.argmin()
        if min_r_cost < -0.001:
            return self.__col_list__[min_r_idx], min_r_cost
        else:
            return None, None

    def __reduced_cost__(self, col, test_dual, vehicle_dual):
        cost = 50 + col.cost
        for tid in col.seq:
            cost -= test_dual[tid]
        cost -= vehicle_dual[col.vid]
        return cost
