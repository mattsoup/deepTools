#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import argparse
import os.path
import numpy as np
from deeptools import parserCommon
from deeptools._version import __version__
import deeptools.getScorePerBigWigBin as score_bw


def parse_arguments(args=None):
    parser = \
        argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description="""

Given two or more bigWig files, bigwigCorrelate computes the average scores for each of the files in every genomic region.
This analysis is performed for the entire genome by running the program in 'bins' mode, or for certain user selected regions in 'BED-file'
mode. Most commonly, the output of bigwigCorrelate is used by other tools such as 'plotCorrelation' or 'plotPCA' for visualization and diagnostic purposes.

detailed sub-commands help available under:

  bigwigCorrelate bins -h

  bigwigCorrelate BED-file -h

""",
            epilog='example usages:\n bigwigCorrelate bins '
                   '-b file1.bw file2.bw -out results.npz\n\n'
                   'bigwigCorrelate BED-file -b file1.bw file2.bw -out results.npz\n'
                   '--BED selection.bed'
                   ' \n\n',
            conflict_handler='resolve')

    parser.add_argument('--version', action='version',
                        version='bigwigCorrelate {}'.format(__version__))
    subparsers = parser.add_subparsers(
        title="commands",
        dest='command',
        metavar='')

    parent_parser = parserCommon.getParentArgParse(binSize=False)
    # read_options_parser = parserCommon.read_options()

    # bins mode options
    subparsers.add_parser(
        'bins',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=[bigwigCorrelateArgs(case='bins'),
                 parent_parser,
                 ],
        help="The average score is based on equally sized bins "
             "(10 kilobases by default), which consecutively cover the "
             "entire genome. The only exception is the last bin of a chromosome, which "
             "is often smaller. The output of this mode is commonly used to assess the "
             "overall similarity of different bigWig files.",
        add_help=False,
        usage='bigWigCorrelate '
              '-b file1.bw file2.bw '
              '-out results.npz\n')

    # BED file arguments
    subparsers.add_parser(
        'BED-file',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=[bigwigCorrelateArgs(case='BED-file'),
                 parent_parser],
        help="The user provides a BED file that contains all regions "
             "that should be considered for the analysis. A "
             "common use is to compare scores (e.g. ChIP-seq scores) between "
             "different samples over a set of pre-defined peak regions.",
        usage='bigwigCorrelate '
              '-b file1.bw file2.bw '
              '-out results.npz --BED selection.bed\n',
        add_help=False)

    return parser


def process_args(args=None):
    args = parse_arguments().parse_args(args)

    if args.labels and len(args.bwfiles) != len(args.labels):
        print "The number of labels does not match the number of bigWig files."
        exit(0)
    if not args.labels:
        args.labels = []
        for f in args.bwfiles:
            if f.startswith("http://") or f.startswith("https://") or f.startswith("ftp://"):
                args.labels.append(f.split("/")[-1])
            else:
                args.labels.append(os.path.basename(f))

    return args


def bigwigCorrelateArgs(case='bins'):
    parser = argparse.ArgumentParser(add_help=False)
    required = parser.add_argument_group('Required arguments')

    # define the arguments
    required.add_argument('--bwfiles', '-b',
                          metavar='FILE1 FILE2',
                          help='List of bigWig files, separated by spaces.',
                          nargs='+',
                          required=True)

    required.add_argument('--outFileName', '-out',
                          help='File name to save the compressed matrix file (npz format)'
                          'needed by the "plotHeatmap" and "plotProfile" tools.',
                          type=argparse.FileType('w'),
                          required=True)

    optional = parser.add_argument_group('Optional arguments')

    optional.add_argument("--help", "-h", action="help",
                          help="show this help message and exit")
    optional.add_argument('--labels', '-l',
                          metavar='sample1 sample2',
                          help='User defined labels instead of default labels from '
                          'file names. '
                          'Multiple labels have to be separated by spaces, e.g., '
                          '--labels sample1 sample2 sample3',
                          nargs='+')

    optional.add_argument('--chromosomesToSkip',
                          metavar='chr1 chr2',
                          help='List of chromosomes that you do not want to be included '
                          'for the correlation. Useful to remove "random" or "extra" chr.',
                          nargs='+')

    if case == 'bins':
        optional.add_argument('--binSize', '-bs',
                              metavar='INT',
                              help='Size (in bases) of the windows sampled '
                              'from the genome.',
                              default=10000,
                              type=int)

        optional.add_argument('--distanceBetweenBins', '-n',
                              metavar='INT',
                              help='By default, bigwigCorrelate considers adjacent '
                              'bins of the specified --binSize. However, to '
                              'reduce the computation time, a larger distance '
                              'between bins can be given. Larger distances '
                              'results in fewer considered bins.',
                              default=0,
                              type=int)

        required.add_argument('--BED',
                              help=argparse.SUPPRESS,
                              default=None)
    else:
        optional.add_argument('--binSize', '-bs',
                              help=argparse.SUPPRESS,
                              default=10000,
                              type=int)

        optional.add_argument('--distanceBetweenBins', '-n',
                              help=argparse.SUPPRESS,
                              metavar='INT',
                              default=0,
                              type=int)

        required.add_argument('--BED',
                              help='Limits the correlation analysis to '
                              'the regions specified in this file.',
                              metavar='bedfile',
                              type=argparse.FileType('r'),
                              required=True)

    group = parser.add_argument_group('Output optional options')

    group.add_argument('--outRawCounts',
                       help='Save raw scores in each bigWig file to a single uncompressed file.',
                       metavar='FILE',
                       type=argparse.FileType('w'))

    return parser


def main(args=None):
    """
    1. get read counts at different positions either
    all of same length or from genomic regions from the BED file

    2. compute  correlation

    """
    args = process_args(args)

    if len(args.bwfiles) < 2:
        print "Please input at least two bigWig (.bw) files to compare"
        exit(1)

    if 'BED' in args:
        bed_regions = args.BED
    else:
        bed_regions = None

    bwFiles = args.bwfiles

    if len(bwFiles) == 0:
        print "No valid bigwig files"
        exit(1)

    num_reads_per_bin = score_bw.getScorePerBin(
        bwFiles,
        args.binSize,
        numberOfProcessors=args.numberOfProcessors,
        stepSize=args.binSize + args.distanceBetweenBins,
        verbose=args.verbose,
        region=args.region,
        bedFile=bed_regions,
        chrsToSkip=args.chromosomesToSkip,
        out_file_for_raw_data=args.outRawCounts)

    sys.stderr.write("Number of bins "
                     "found: {}\n".format(num_reads_per_bin.shape[0]))

    if num_reads_per_bin.shape[0] < 2:
        exit("ERROR: too few non zero bins found.\n"
             "If using --region please check that this "
             "region is covered by reads.\n")

    np.savez_compressed(args.outFileName,
                        matrix=num_reads_per_bin,
                        labels=args.labels)

    if args.outRawCounts:
        # append to the generated file the
        # labels
        header = "#'chr'\t'start'\t'end'\t"
        header += "'" + "'\t'".join(args.labels) + "'\n"
        # import ipdb;ipdb.set_trace()
        with open(args.outRawCounts.name, 'r+') as f:
            content = f.read()
            f.seek(0, 0)
            f.write(header + content)

        """
        if bed_regions:
            bed_regions.seek(0)
            reg_list = bed_regions.readlines()
            args.outRawCounts.write("#'chr'\t'start'\t'end'\t")
            args.outRawCounts.write("'" + "'\t'".join(args.labels) + "'\n")
            fmt = "\t".join(np.repeat('%s', num_reads_per_bin.shape[1])) + "\n"
            for idx, row in enumerate(num_reads_per_bin):
                args.outRawCounts.write("{}\t{}\t{}\t".format(*reg_list[idx].strip().split("\t")[0:3]))
                args.outRawCounts.write(fmt % tuple(row))

        else:
            args.outRawCounts.write("'" + "'\t'".join(args.labels) + "'\n")
            fmt = "\t".join(np.repeat('{}', num_reads_per_bin.shape[1])) + "\n"
            for row in num_reads_per_bin:
                args.outRawCounts.write(fmt.format(*tuple(row)))
        """
