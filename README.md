Fitting symmetric and non-symmetric finite Determinant Point Process (DPP) kernels
=============

## Requirements
- Python 3: [Anaconda](https://www.anaconda.com/download/) is recommended
- Python libraries: chainer:  `pip install chainer`

# How to use

To create sample data,
```
python gen_powersets.py --rankV 2 --rankB 1 -n 1000 --dim 5 > V2B1.csv
```
Each row of csv contains a subset of {0,...,_dim_-1} according to the probability specified by a random matrix L with rank _rankV_ symmetric part and rank _rankB_ anti-symmetric part.
The total number of samples is _n_.

To fit the DPP model to data,
```
python trainDPP.py --train V2B1.csv --rankV 2 --rankB 1 --dim 5 --epoch 200
```
The result will be saved under _outdir_.
It contains, above all, the fitted matrix L.csv and its components V.csv (diagonal), B.csv and C.csv (Cholesky components of the anti-symmetric part).
See the class definition of DPP in trainDPP.py for the explicit relation between L and V,B,C.

There are many parameters to be tuned.
```
python trainDPP.py -h
```
gives the list of command-line arguments.
