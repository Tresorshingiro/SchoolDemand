"""Data imports from the admin portal: read a file, check it into a report, publish it as the live data.

  tables.py   read .xlsx / .csv, match column names
  report.py   errors (block Publish), warnings, changes, the rows concerned
  rooms.py    the physical room ID (test_code) from classroom_id
  checks.py   the checks of each kind of file
  publish.py  write the live tables
  service.py  uploads, the import lifecycle, the background worker's jobs
"""
