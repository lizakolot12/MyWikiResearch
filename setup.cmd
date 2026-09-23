@echo off
rem Run once after `git clone` (Windows): installs the wiki-interest skill for Claude Code.
rem   setup.cmd                 install
rem   setup.cmd claude haiku    install, then start Claude Code on Claude Haiku 4.5
cd /d "%~dp0"
where py >nul 2>nul && (py -3 wiki-interest\install.py %* & exit /b %errorlevel%)
where python >nul 2>nul && (python wiki-interest\install.py %* & exit /b %errorlevel%)
echo Python 3.10+ is required: https://www.python.org/downloads/
exit /b 1
