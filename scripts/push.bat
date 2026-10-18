@echo off
cd /d "%~dp0"

git add .

for /f %%i in ('powershell -NoProfile -Command "$tz=[TimeZoneInfo]::FindSystemTimeZoneById(''India Standard Time''); $t=[TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow,$tz); $t.ToString(''mmHHddMMyyyy'')"') do set COMMIT=%%i

echo Commit: %COMMIT%

git commit -m "%COMMIT%"
git push -u origin mdev

pause