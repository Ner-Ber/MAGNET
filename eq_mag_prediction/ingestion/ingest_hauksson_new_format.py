# coding=utf-8
# Copyright 2025 The Google Research Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Ingests the raw Hauksson focal mechanism catalog.

The format appears here:
https://service.scedc.caltech.edu/ftp/catalogs/hauksson/Socal_focal/SouthernCalifornia_1981-2011_focalmec_Format.pdf
"""

import io  # Add this to your imports
import glob
import math
import os

from absl import app
from absl import flags
import numpy as np
import pandas as pd

from tensorflow.io import gfile
from eq_mag_prediction.utilities import data_utils
from eq_mag_prediction.utilities import time_conversions

_RAW_DIRECTORY = flags.DEFINE_string(
    'raw_directory',
    os.path.join(
        os.path.dirname(__file__), '../..', 'results/catalogs/raw/Hauksson'
    ),
    'The directory that contains the raw catalog files.',
)
_INGESTED_FILE = flags.DEFINE_string(
    'ingested_directory',
    os.path.join(
        os.path.dirname(__file__),
        '../..',
        'results/catalogs/ingested/hauksson.csv',
    ),
    'The path to the ingested CSV file.',
)


def parse_file(path):
  """Parses a single raw catalog file in the Hauksson 2012 fixed-width format."""

  # Define the fixed-width column specifications based on the 146-char format.
  # Tuples are (start_index, end_index).
  colspecs = [
      (0, 4),     # year
      (5, 7),     # month
      (8, 10),    # day
      (11, 13),   # hour
      (14, 16),   # minute
      (17, 23),   # second
      (24, 33),   # event_id (CUSPID)
      (34, 43),   # latitude
      (44, 54),   # longitude
      (55, 62),   # depth
      (63, 68),   # magnitude
  ]

  names = [
      'year', 'month', 'day', 'hour', 'minute', 'second',
      'event_id', 'latitude', 'longitude', 'depth', 'magnitude'
  ]

  # Filter out header lines (metadata) and keep only lines starting with a digit.
  with open(path, 'r') as f:
    # We assume data lines start with a 4-digit year (e.g., "1981").
    data_lines = [line for line in f if line[:4].strip().isdigit()]
    # counter = 0
    # data_lines = []
    # for line in f:
    #   if line[:4].strip().isdigit():
    #     data_lines.append(line)
    #   if counter > 1000:
    #     break

  # Parse the filtered data
  if not data_lines:
    return pd.DataFrame(columns=names)

  return pd.read_fwf(
      io.StringIO('\n'.join(data_lines)),
      colspecs=colspecs,
      header=None,
      names=names
  )


def clean_catalog(catalog):
  """Adds useful columns, removes unused ones. Optimized."""

  # It is also unclear why these exist. There are ~5 of those, and all have a small
  # magnitude.
  minutes = catalog['minute'].to_numpy(copy=True)
  minutes[minutes == -1] = 0  # Bulk replace -1 with 0

  # Separate integer seconds and microseconds
  seconds_float = catalog['second'].to_numpy()
  sec_int = np.floor(seconds_float).astype(int)
  # It is unclear why these exists. There are ~10 of these in the catalog,
  # all of a fairly small magnitude, so they probably won't have a huge
  # impact.
  sec_int[sec_int == 60] = 59

  # Calculate microseconds: (fractional_part * 1e6)
  # We round to nearest int to avoid floating point weirdness like 0.999999
  microseconds = np.rint((seconds_float % 1) * 1e6).astype(int)

  dt_series = pd.to_datetime({
      'year': catalog['year'],
      'month': catalog['month'],
      'day': catalog['day'],
      'hour': catalog['hour'],
      'minute': minutes,
      'second': sec_int,
      'microsecond': microseconds
  })
  catalog['time'] = dt_series.values.view('int64') / 1e9

  # dt_components = pd.DataFrame({
  #     'year': catalog['year'],
  #     'month': catalog['month'],
  #     'day': catalog['day'],
  #     'hour': catalog['hour'],
  #     'minute': minutes,
  #     'second': sec_int
  # })

  # timestamps = pd.to_datetime(dt_components)
  # catalog['time'] = timestamps + pd.to_timedelta(microseconds, unit='us')
  # # Convert pandas Timestamp to float seconds (Unix epoch)
  # catalog['time'] = (catalog['time'] - pd.Timestamp("1970-01-01")
  #                    ) // pd.Timedelta('1us') / 1e6

  catalog['x_utm'], catalog['y_utm'] = data_utils.PROJECTIONS['california'](
      catalog['longitude'].values, catalog['latitude'].values
  )
  return catalog


def clean_catalog_old(catalog):
  """Adds useful columns, removes unused ones."""
  time_column = []
  for i in range(len(catalog)):
    second = math.floor(catalog.second.iloc[i])
    if second == 60:
      # It is unclear why these exists. There are ~10 of these in the catalog,
      # all of a fairly small magnitude, so they probably won't have a huge
      # impact.
      second -= 1
    minute = catalog.minute.iloc[i]
    if minute == -1:
      # It is also unclear why these exist. Again, there are ~5 of those, and
      # all have a small magnitude.
      minute += 1
    microsecond = int((catalog.second.iloc[i] % 1) * 1e6)
    time_column.append(
        time_conversions.datetime_utc_to_time(
            year=catalog.year.iloc[i],
            month=catalog.month.iloc[i],
            day=catalog.day.iloc[i],
            hour=catalog.hour.iloc[i],
            minute=minute,
            second=second,
            microsecond=microsecond,
        )
    )
  catalog['time'] = time_column

  catalog['x_utm'], catalog['y_utm'] = data_utils.PROJECTIONS['california'](
      catalog['longitude'].values, catalog['latitude'].values
  )
  # catalog = catalog.drop(
  #     columns=['unused1', 'unused2', 'unused3', 'unused4', 'unused5']
  # )
  return catalog


def main(_):
  result = pd.concat(
      [parse_file(path) for path in glob.glob(f'{_RAW_DIRECTORY.value}/*')]
  )

  result = clean_catalog(result)
  # result = clean_catalog_old(result)

  with open(_INGESTED_FILE.value, 'wt') as f:
    result.to_csv(f, index=False)


if __name__ == '__main__':
  app.run(main)
