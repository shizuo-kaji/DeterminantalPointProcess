#!/usr/bin/env python
# -*- coding: utf-8 -*-
# DPP kernel fitter
# S. Kaji
# Dec. 2019

from __future__ import print_function
import matplotlib as mpl
mpl.use('Agg')

import numpy as np
import pandas as pd
import argparse
import functools
import random
import chainer
import chainer.functions as F
import chainer.links as L
from chainer import training,datasets,iterators
from chainer.training import extensions,triggers
from chainer.dataset import dataset_mixin, convert, concat_examples
from chainerui.utils import save_args
import os,shutil,glob
from datetime import datetime as dt

from consts import optim,dtypes

class DPP(chainer.Chain):
    def __init__(self, dim, rankV, rankB, n_hidden_channels):
        super().__init__()
        self.n_hidden_channels = n_hidden_channels
        self.dim = dim
        self.rankV = rankV
        self.rankB = rankB
        with self.init_scope():
            for i in range(len(n_hidden_channels)):
                setattr(self, 'l' + str(i), L.Linear(None,n_hidden_channels[i]))
            if rankV>0:
                self.V = chainer.Parameter(np.random.uniform(low=-2.0, high=2.0, size=(dim, rankV)))
            if rankB>0:
                self.B = chainer.Parameter(np.random.uniform(low=-2.0, high=2.0, size=(dim, rankB)))
                self.C = chainer.Parameter(np.random.uniform(low=-2.0, high=2.0, size=(dim, rankB)))

    def __call__(self, x):
        h=x
        L = self.xp.zeros((self.dim,self.dim))
        for i in range(len(self.n_hidden_channels)):
            h=getattr(self, 'l' + str(i))(h)
            if i < len(self.n_hidden_channels)-1:
                h=F.tanh(h)
        if self.rankV>0:
            if len(self.n_hidden_channels)>0:
                L += F.matmul(self.V * F.exp(h), self.V, transb=True)
            else:
                L += F.matmul(self.V, self.V, transb=True)
        if self.rankB>0:
            AS = F.matmul(self.B,self.C,transb=True)
            L += AS - AS.T
        return L

## dataset preparation
class Dataset(dataset_mixin.DatasetMixin):
    def __init__(self, path):
        self.path = path
        self.dat = []
        self.maxid = 0
        with open(path) as infh:
            for line in infh:
#                print(line,len(line))
                if len(line)>1:
                    l = np.array(line.strip().split(','),dtype=np.int)
                    self.maxid = max(self.maxid,max(l))
                else:
                    l = []
                self.dat.append(l)
        print("Data loaded: {}, Max ID: {}".format(len(self.dat),self.maxid))
    def __len__(self):
        return len(self.dat)

    def get_example(self, i):
        return (self.dat[i])

# evaluator
class Evaluator(extensions.Evaluator):
    name = "myval"
    def __init__(self, *args, **kwargs):
        params = kwargs.pop('params')
        super(Evaluator, self).__init__(*args, **kwargs)
        self.count = 0
    def evaluate(self):
        model = self.get_target('main')
        L = model(0) # fixed input for now
        if self.eval_hook:
            self.eval_hook(self)
        loss = 0
        n = 0
        test_iter=self.get_iterator('main')
        while True:
            batch = test_iter.next()
            if model.rankV==0:
                for b in batch:
                    if len(b) % 2 ==0:
                        if len(b)>0:
                            loss -= F.log(F.det(L[b,:][:,b]))
                        n += 1
            else:
                for b in batch:
                    if len(b)>0:
                        loss -= F.log(F.det(L[b,:][:,b]))
                n += len(batch)
            if test_iter.is_new_epoch:
                test_iter.reset()
                break
        loss /= max(n,1)                
    #   filename = "result_{}.csv".format(self.count)
        loss += F.log(F.det(model.xp.eye(L.shape[0])+L))
        self.count += 1
        return {"myval/loss":loss}

## updater 
class Updater(chainer.training.StandardUpdater):
    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop('models')
        params = kwargs.pop('params')
        super(Updater, self).__init__(*args, **kwargs)
        self.args = params['args']

    def update_core(self):
        opt = self.get_optimizer('main')
        L = self.model(0) # fixed input for now
#        print(L.shape)
        batch = self.get_iterator('main').next()
        loss = 0
        if self.model.rankV==0:
            n=0
            for b in batch:
                if len(b) % 2 ==0:
                    if len(b)>0:
                        loss -= F.log(F.det(L[b,:][:,b]))
                    n += 1
            loss /= max(n,1)
        else:
            for b in batch:
                if len(b)>0:
                    loss -= F.log(F.det(L[b,:][:,b]))
            loss /= len(batch)
        nm = F.det(self.model.xp.eye(L.shape[0])+L)
        loss += F.log(nm)
        self.model.cleargrads()
        loss.backward()
        opt.update(loss=loss)
        chainer.report({'loss': loss}, self.model)

########################################################
def main():
    # command line argument parsing
    parser = argparse.ArgumentParser(description='Fitting non-symmetric DPP kernels to data')
    parser.add_argument('--train', '-t', default="cv0",help='Path to csv file')
    parser.add_argument('--val', help='Path to validation csv file')
    parser.add_argument('--outdir', '-o', default='result',
                        help='Directory to output the result')
    parser.add_argument('--epoch', '-e', type=int, default=200,
                        help='Number of sweeps over the dataset to train')
    parser.add_argument('--gpu', '-g', type=int, default=-1,
                        help='GPU ID (negative value indicates CPU)')
    parser.add_argument('--models', '-m', default=None, help='load pretrained models')
    parser.add_argument('--early_stopping', '-es', type=int, default=0, help='')
    parser.add_argument('--rankV', '-rv', type=int, default=2, help='rank of V')
    parser.add_argument('--rankB', '-rb', type=int, default=0, help='rank of B')
    parser.add_argument('--dim', '-d', default=None, help='dimension of the kernel (number of items)')
    parser.add_argument('--n_hidden_channels', '-chs', type=int, nargs="*", default=[],
                        help='number of channels of hidden layers for diagonal entry')
    parser.add_argument('--batchsize', '-b', type=int, default=20,
                        help='Number of samples in each mini-batch')
    parser.add_argument('--predict', '-p', action='store_true', help='prediction with a specified model')
    parser.add_argument('--optimizer', '-op',choices=optim.keys(),default='Adam',
                        help='optimizer')
    parser.add_argument('--learning_rate', '-lr', type=float, default=1e-2,
                        help='learning rate')
    parser.add_argument('--weight_decay_l1', '-wd1', type=float, default=0,
                        help='L1 weight decay for regularization')
    parser.add_argument('--weight_decay_l2', '-wd2', type=float, default=0,
                        help='L2 weight decay for regularization')
    parser.add_argument('--dtype', '-dt', choices=dtypes.keys(), default='fp32',
                        help='floating point precision')
    parser.add_argument('--vis_freq', '-vf', type=int, default=200,
                        help='output frequency in iteration')
    args = parser.parse_args()

    dtime = dt.now().strftime('%m%d_%H%M')
    args.outdir = os.path.join(args.outdir, '{}'.format(dtime))
    # Enable autotuner of cuDNN
    chainer.config.autotune = True
    chainer.config.dtype = dtypes[args.dtype]
    chainer.print_runtime_info()
    print(args)
    save_args(args, args.outdir)

    # data
    train = Dataset(args.train)
    if not args.dim:
        args.dim = train.maxid+1
    if args.val:
        test = Dataset(args.val)
    else:
        test = Dataset(args.train)
    train_iter = iterators.SerialIterator(train, args.batchsize, shuffle=True)
    test_iter = iterators.SerialIterator(test, args.batchsize, repeat=False, shuffle=False)

    # initialise kernel components
    model = DPP(args.dim, args.rankV, args.rankB, args.n_hidden_channels)

    # Set up an optimizer
    optimizer = optim[args.optimizer](args.learning_rate)
    optimizer.setup(model)
    if args.weight_decay_l2>0:
        if args.optimizer in ['Adam','AdaBound','Eve']:
            optimizer.weight_decay_rate = args.weight_decay
        else:
            optimizer.add_hook(chainer.optimizer.WeightDecay(args.weight_decay_l2))
    if args.weight_decay_l1>0:
        optimizer.add_hook(chainer.optimizer_hooks.Lasso(args.weight_decay_l1))

    if args.models:
        chainer.serializers.load_npz(args.models,model)
        print('model loaded: {}'.format(args.models))
        
    if args.gpu >= 0:
        chainer.cuda.get_device(args.gpu).use()
        model.to_gpu()
        
    updater = Updater(
        models=model,
        iterator=train_iter,
        optimizer={'main': optimizer},
        device=args.gpu,
        params={'args': args}
        )

    log_interval = 1, 'epoch'
    if args.early_stopping:
        stop_trigger = triggers.EarlyStoppingTrigger(
            monitor='myval/loss',
            check_trigger=(args.early_stopping, 'epoch'),
            max_trigger=(args.epoch, 'epoch'))
    else:
        stop_trigger = (args.epoch, 'epoch')
    trainer = training.Trainer(updater, stop_trigger, out=args.outdir)
    trainer.extend(extensions.LogReport(trigger=log_interval))
#    trainer.extend(extensions.dump_graph('main/loss'))
    if args.optimizer in ['SGD','Momentum','AdaGrad','RMSprop']:
        trainer.extend(extensions.observe_lr(), trigger=log_interval)
        trainer.extend(extensions.ExponentialShift('lr', 0.5), trigger=(args.epoch/1, 'epoch'))
    elif args.optimizer in ['Adam','AdaBound','Eve']:
        trainer.extend(extensions.observe_lr(), trigger=log_interval)
        trainer.extend(extensions.ExponentialShift("alpha", 0.5, optimizer=optimizer), trigger=(args.epoch/1, 'epoch'))

    if extensions.PlotReport.available():
        trainer.extend(extensions.PlotReport(['main/loss','myval/loss'],
                                  'epoch', file_name='loss.png'))

    trainer.extend(extensions.PrintReport([
            'epoch', 'main/loss','myval/loss',
          'elapsed_time', 'lr'
         ]),trigger=log_interval)

    trainer.extend(extensions.ProgressBar(update_interval=10))
    trainer.extend(Evaluator(test_iter, model, params={'args': args}, device=args.gpu),trigger=(args.vis_freq, 'iteration'))

    if not args.predict:
        trainer.run()

    # histogram of DPP
    pivot = 0
    L=model(0).array
    if args.gpu>-1:
        L=L.get()
    np.savetxt(os.path.join(args.outdir,"L.csv"),L)
    if args.rankV>0:
        np.savetxt(os.path.join(args.outdir,"V.csv"),model.V.array)
    if args.rankB>0:
        np.savetxt(os.path.join(args.outdir,"B.csv"),model.B.array)
        np.savetxt(os.path.join(args.outdir,"C.csv"),model.C.array)

    nm = np.linalg.det(np.eye(L.shape[0])+L)
    p_dat = np.zeros(args.dim)
    p = np.zeros(args.dim)
    p[0] = L[pivot,pivot]/nm
    for i in range(pivot+1,args.dim):
        p[i] = np.linalg.det(L[[pivot,i],:][:,[pivot,i]])/nm
    # histogram of data
    p_dat = np.zeros(args.dim)
    for b in train:
        if pivot in b:
            if len(b)==1:
                p_dat[0] += 1
            elif len(b)==2 and b[1]>pivot:
                p_dat[b[1]] += 1
    p_dat /= len(train)
    print("\n Probability of DPP")
    print(np.around(p,5))
    print("\n Probability of data")
    print(np.around(p_dat,5))

if __name__ == '__main__':
    main()