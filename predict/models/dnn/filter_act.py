#!/usr/bin/env python

import argparse
import sys
import logging
import os.path as pt
import numpy as np
import h5py as h5
import theano as th

import predict.models.dnn.utils as ut
import predict.models.dnn.model as mod


def write_activations(data, name, out_file):
    f = h5.File(out_file, 'a')
    if 'act' not in f:
        f.create_group('act')
    g = f['act']
    if name in g:
        del f[name]
    g = g.create_group(name)

    for chromo in np.unique(data['chromo']):
        t = data['chromo'] == chromo
        dc = {k: data[k][t] for k in data.keys()}
        t = np.argsort(dc['pos'])
        for k in dc.keys():
            dc[k] = dc[k][t]
        t = dc['pos']
        assert np.all(t[:-1] < t[1:])
        gc = g.create_group(chromo)
        for k in dc.keys():
            if k != 'chromo':
                gc[k] = dc[k]
    f.close()


class App(object):

    def run(self, args):
        name = pt.basename(args[0])
        parser = self.create_parser(name)
        opts = parser.parse_args(args[1:])
        self.opts = opts
        return self.main(name, opts)

    def create_parser(self, name):
        p = argparse.ArgumentParser(
            prog=name,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            description='Compute filter activations')
        p.add_argument(
            'data_file',
            help='Data file')
        p.add_argument(
            '--model',
            help='Model files',
            nargs='+')
        p.add_argument(
            '-o', '--out_file',
            help='Output file')
        p.add_argument(
            '--predict_file',
            help='Also make prediction')
        p.add_argument(
            '--conv_layer',
            help='Convolutional layer',
            default='s_c1')
        p.add_argument(
            '--chromo',
            help='Chromosome')
        p.add_argument(
            '--start',
            help='Start position',
            type=int)
        p.add_argument(
            '--end',
            help='End position',
            type=int)
        p.add_argument(
            '--nb_sample',
            help='Maximum # training samples',
            type=int)
        p.add_argument(
            '--batch_size',
            help='Batch size',
            type=int,
            default=128)
        p.add_argument(
            '--max_mem',
            help='Maximum memory load',
            type=int,
            default=14000)
        p.add_argument(
            '--seed',
            help='Seed of rng',
            type=int,
            default=0)
        p.add_argument(
            '--verbose',
            help='More detailed log messages',
            action='store_true')
        p.add_argument(
            '--log_file',
            help='Write log messages to file')
        return p

    def main(self, name, opts):
        logging.basicConfig(filename=opts.log_file,
                            format='%(levelname)s (%(asctime)s): %(message)s')
        log = logging.getLogger(name)
        if opts.verbose:
            log.setLevel(logging.DEBUG)
        else:
            log.setLevel(logging.INFO)
            log.debug(opts)

        if opts.seed is not None:
            np.random.seed(opts.seed)

        log.info('Load data')

        def read_data(path):
            f = ut.open_hdf(path, cache_size=opts.max_mem)
            data = dict()
            for k, v in f['data'].items():
                data[k] = v
            for k, v in f['pos'].items():
                data[k] = v
            return (f, data)

        labels = ut.read_labels(opts.data_file)
        data_file, data = read_data(opts.data_file)

        if opts.chromo is not None:
            sel = data['chromo'].value == str(opts.chromo).encode()
            if opts.start is not None:
                sel &= data['pos'].value >= opts.start
            if opts.end is not None:
                sel &= data['pos'].value <= opts.end
            if sel.sum() == 0:
                log.warn('No samples satisfy filter!')
                return 0
            log.info('Select %d samples' % (sel.sum()))
            for k in data.keys():
                if len(data[k].shape) > 1:
                    data[k] = data[k][sel, :]
                else:
                    data[k] = data[k][sel]

        def to_view(d):
            for k in d.keys():
                d[k] = ut.ArrayView(d[k], stop=opts.nb_sample)

        to_view(data)
        log.info('%d samples' % (list(data.values())[0].shape[0]))

        log.info('Load model')
        model = mod.model_from_list(opts.model, compile=True)

        def progress(batch, nb_batch):
            batch += 1
            c = max(1, int(np.ceil(nb_batch / 50)))
            if batch == 1 or batch == nb_batch or batch % c == 0:
                print('%5d / %d (%.1f%%)' % (batch, nb_batch,
                                             batch / nb_batch * 100))

        def predict(d=data):
            z = model.predict(d, verbose=opts.verbose,
                              batch_size=opts.batch_size, callbacks=[progress])
            return z

        if opts.predict_file is not None:
            log.info('Predict')
            z = predict()
            ut.write_z(data, z, labels, opts.predict_file, unlabeled=True,
                       name='z')

        log.info('Compute sequence filter activations')
        x = model.get_input(train=False)['s_x']
        y = model.nodes['s_c1'].get_output(train=False)
        f = th.function([x], y)
        fy = f(data['s_x'])
        d = dict(chromo=data['chromo'][:], pos=data['pos'][:], y=fy)
        write_activations(d, 's_x', opts.out_file)

        data_file.close()
        log.info('Done!')

        return 0


if __name__ == '__main__':
    app = App()
    app.run(sys.argv)
