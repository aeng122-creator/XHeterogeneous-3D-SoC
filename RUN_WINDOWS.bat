@echo off
cd /d "%~dp0"
py -3 sim\model.py --cycles 1800 --out results\windows_run.json
py -3 -m sim.report results\windows_run.json results
py -3 -m unittest discover -s tests -v
pause
