import math
from random import random


def to_6(t):
    num_zs = 6 - len(t)
    return "0" * num_zs + t


def gen_otp():
    t_otp = str(math.floor(random() * 1000000))
    otp = to_6(t_otp)
    return int(otp)
