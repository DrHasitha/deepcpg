from keras.callbacks import Callback
import pandas as pd
import numpy as np


class LearningRateScheduler(Callback):

    def __init__(self, callback, monitor='val_loss', patience=0):
        super(LearningRateScheduler, self).__init__()
        self.callback = callback
        self.patience = patience
        self.monitor = monitor

        self.counter = 0
        self.prev_score = np.inf
        self.best_score = np.inf
        self.best_weights = None

    def on_epoch_end(self, epoch, logs={}):
        score = logs.get(self.monitor)
        if score <= self.prev_score:
            self.counter = 0
            if score <= self.best_score:
                self.best_score = score
                self.best_weights = self.model.get_weights()
        else:
            self.counter += 1
            if self.counter > self.patience:
                self.callback()
                self.model.set_weights(self.best_weights)
                self.counter = 0
        self.prev_score = score


class PerformanceLogger(Callback):

    def __init__(self, batch_logs=['loss', 'acc'], epoch_logs=['val_loss', 'val_acc']):
        if batch_logs is None:
            batch_logs = []
        if epoch_logs is None:
            epoch_logs = []
        self.batch_logs = batch_logs
        self.epoch_logs = epoch_logs

    def on_train_begin(self, logs={}):
        self._batch_logs = []
        self._epoch_logs = []

    def on_epoch_begin(self, epoch, logs={}):
        self._batch_logs.append([])

    def on_batch_end(self, batch, logs={}):
        l = {k: v for k, v in logs.items() if k in self.batch_logs}
        self._batch_logs[-1].append(l)

    def on_epoch_end(self, batch, logs={}):
        l = {k: v for k, v in logs.items() if k in self.epoch_logs}
        self._epoch_logs.append(l)

    def _list_to_frame(self, l, keys):
        keys = [k for k in keys if k in l[0].keys()]
        d = {k: [] for k in keys}
        for ll in l:
            for k in keys:
                d[k].append(float(ll[k]))
        d = pd.DataFrame(d, columns=keys)
        return d

    def epoch_frame(self):
        d = self._list_to_frame(self._epoch_logs, self.epoch_logs)
        t = list(d.columns)
        d['epoch'] = np.arange(d.shape[0]) + 1
        d = d.loc[:, ['epoch'] + t]
        return d

    def batch_frame(self, epoch=None):
        if epoch is None:
            d = []
            for e in range(len(self._batch_logs)):
                de = self.batch_frame(e + 1)
                t = list(de.columns)
                de['epoch'] = e + 1
                de = de.loc[:, ['epoch'] + t]
                d.append(de)
            d = pd.concat(d)
        else:
            d = self._list_to_frame(self._batch_logs[epoch - 1], self.batch_logs)
            t = list(d.columns)
            d['batch'] = np.arange(d.shape[0]) + 1
            d = d.loc[:, ['batch'] + t]
        return d

    def frame(self):
        b = self.batch_frame().groupby('epoch', as_index=False).mean()
        b = b.loc[:, b.columns != 'batch']
        e = self.epoch_frame()
        c = pd.merge(b, e, on='epoch')
        return c