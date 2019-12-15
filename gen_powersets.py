#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
import numpy as np
import argparse
import os
import itertools

# command line argument parsing
parser = argparse.ArgumentParser(description='Generate power sets of a finite set')
parser.add_argument('--rankV', '-rv', type=int, default=2, help='rank of V (symmetric part)')
parser.add_argument('--rankB', '-rb', type=int, default=0, help='rank of B (anti-symmetric part)')
parser.add_argument('--n', '-n', default=100, help='number of samples')
parser.add_argument('--dim', '-d', default=5, type=int, help='dimension')
parser.add_argument('--random', '-r', action='store_true', help='random choice')
args = parser.parse_args()

l = np.arange(args.dim)

if args.random:
    for i in range(args.n):
        m = np.random.randint(args.rankV)+1
        print(",".join(map(str,np.random.permutation(l)[:m])))
else:
    L = np.zeros((args.dim,args.dim))
    if args.rankV>0:
        V = np.random.uniform(low=-2.0, high=2.0, size=(args.dim, args.rankV))
        L += np.matmul(V, V.T)
    if args.rankB>0:
        B = np.random.uniform(low=-2.0, high=2.0, size=(args.dim, args.rankB))
        C = np.random.uniform(low=-2.0, high=2.0, size=(args.dim, args.rankB))
        AS = np.matmul(B,C.T)
        L += AS - AS.T
    ## TODO: sampling
    nm = np.linalg.det(np.eye(L.shape[0])+L)
    sum_p=1/nm
    for i in range(int(round(sum_p*args.n,None))):
        print()
#    print(L,nm)
    for m in range(1,max(args.rankV,args.rankB)+1):
        for b in itertools.combinations(l,m):
            p = np.linalg.det(L[b,:][:,b])/nm
            sum_p += p
#            print(L[b,:][:,b],b,p)
            for i in range(int(round(p*args.n,None))):
                print(",".join(map(str,b)))
#    print(sum_p)
