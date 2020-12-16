#!/usr/bin/env python
import argparse
import csv
import pandas as pd
from multiprocessing import Pool
import os
import logging
from corncob import Corncob
# Set up logging
logFormatter = logging.Formatter(
    '%(asctime)s %(levelname)-8s [corncob] %(message)s'
)
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.INFO)

# Write logs to STDOUT
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

description="""
CORNCOB: beta-binomial based testing of count data.\n
Based on, Martin BD, Witten D, Willis AD. Modeling microbial abundances and dysbiosis with beta-binomial regression. Ann Appl Stat. 2020 Mar;14(1):94-115.
"""
def run_corncob(params):
        (total_counts, e_row, specimens, X, X_star) = params
        e = e_row[0]
        counts = pd.Series([int(c) for c in e_row[1:]], index=specimens)
        cc = Corncob(
            total=total_counts,
            count=counts,
            X=X,
            X_star=X_star
        )
        e_m = cc.fit()
        (abd_res, disp_res) = cc.waltdt()
        return(
            e,
            e_m.success,
            abd_res,
            disp_res,
        )


def main():
    parser = argparse.ArgumentParser(
        description=description
    )
    parser.add_argument(
        '-C', '--counts_csv',
        help='CSV file containing the count data. Must have first row with total count, then each row after the counts for each specimen',
        required=True,
        type=argparse.FileType('rt'),
    )
    parser.add_argument(
        '-VA', '--covariates_abund_csv',
        help='CSV file containing the covariates for abundance. Intercept column automatically added',
        required=False,
    )
    parser.add_argument(
        '-VD', '--covariates_disp_csv',
        help='CSV file containing the covariates for dispersion. Intercept column automatically added',
        required=False,
    )
    parser.add_argument(
        '-O', '--output',
        help='Where to place the results in CSV format',
        required=True,
        type=argparse.FileType('wt')
    )
    parser.add_argument(
        '-T', '--threads',
        help='Number of threads to use. Default is os.cpu_count()',
        type=int,
        default=os.cpu_count()
    )

    args = parser.parse_args()
    logging.info("Loading and verifying count header")
    # Verify count file
    count_reader = csv.reader(args.counts_csv)
    header = next(count_reader)
    specimens = header[1:]
    if len(specimens) != len(set(specimens)):
        raise ValueError("Specimen labels in count are not unique!")
    # Implicit else specimens are unique
    total_count_r = next(count_reader)
    if total_count_r[0].strip() != 'total':
        raise ValueError("First count row is not total count per specimen")
    # Implicit else
    total_counts = pd.Series([int(c) for c in total_count_r[1:]], index=specimens)

    logging.info("Loading and verifying abundance covariates")
    # Load or build exog matrix
    if args.covariates_abund_csv is None:
        # Build it!
        X = pd.DataFrame(index=specimens)
        X['intercept'] = 1
        
    else:
        # Load it
        X = pd.read_csv(args.covariates_abund_csv, index_col=0)
        # Make order match that in counts. Trim if neccesary
        X = X.loc[specimens]
        X['intercept'] = 1
    logging.info("Loading and verifying dispersion covariates")
    # Load or build exog matrix
    if args.covariates_disp_csv is None:
        # Build it!
        X_star = pd.DataFrame(index=specimens)
        X_star['intercept'] = 1
        
    else:
        # Load it
        X_star = pd.read_csv(args.covariates_disp_csv, index_col=0)
        # Make order match that in counts. Trim if neccesary
        X_star = X_star.loc[specimens]
        X_star['intercept'] = 1

    # OK! Now run corncob!
    logging.info("Model fitting (this can be time consuming)")

    with Pool(args.threads) as cc_pool:
        cc_results = cc_pool.map(
            run_corncob,
            [
                (
                    total_counts,
                    e_row,
                    specimens,
                    X,
                    X_star,
                )
                for e_row in count_reader
            ]        
        )
    logging.info("Transforming outputs")
    # Reformat into a wide format for output
    out_df = pd.DataFrame(
        columns=[
            'converged',
        ]+[
        'abd__{}__{}'.format(c, m_o)
        for c in X.columns
        for m_o in ['Estimate', 'se', 't', 'p']
        ] + [
        'disp__{}__{}'.format(c, m_o)
        for c in X_star.columns
        for m_o in ['Estimate', 'se', 't', 'p']
        ]
    )
    
    for (element, converged, abd_res, disp_res) in cc_results:
        out_df.loc[element, 'converged'] = converged
        for c in X.columns:
            for m_o in ['Estimate', 'se', 't', 'p']:
                out_df.loc[element, 'abd__{}__{}'.format(c, m_o)] = abd_res.loc[c, m_o]
        for c in X_star.columns:
            for m_o in ['Estimate', 'se', 't', 'p']:
                out_df.loc[element, 'disp__{}__{}'.format(c, m_o)] = disp_res.loc[c, m_o]

    out_df.to_csv(args.output)

    
if __name__ == '__main__':
    main()