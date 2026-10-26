"""Windows Task Scheduler registration for the `serve` process (starts at logon)."""
from __future__ import annotations
import getpass
import os
import subprocess
import sys
from pathlib import Path

from .paths import ROOT, SCHEDULER_DIR

TASK_NAME = "Soundbar Deal Bot"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return cand if cand.exists() else exe


def task_xml() -> str:
    user = os.environ.get("USERDOMAIN", "") + "\\" + getpass.getuser() if os.environ.get("USERDOMAIN") else getpass.getuser()
    exe = _pythonw()
    main_py = ROOT / "main.py"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Soundbar Deal Bot: watches Cypriot and Greek shops for true Dolby Atmos soundbar offers and serves the local dashboard.</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{user}</UserId>
      <Delay>PT1M</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{exe}</Command>
      <Arguments>"{main_py}" serve</Arguments>
      <WorkingDirectory>{ROOT}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def install() -> str:
    SCHEDULER_DIR.mkdir(exist_ok=True)
    xml_path = SCHEDULER_DIR / "task.xml"
    xml_path.write_text(task_xml(), encoding="utf-16")
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"schtasks failed ({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
    return f"Task '{TASK_NAME}' registered from {xml_path}\n{r.stdout.strip()}"


def uninstall() -> str:
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"schtasks failed ({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
    return f"Task '{TASK_NAME}' removed"


def query() -> str:
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else f"not registered ({r.stderr.strip()})"


def restart_task() -> str:
    """End the running instance cleanly (not recorded as a crash), then start it again."""
    subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], capture_output=True, text=True)
    return run_task()


def run_task() -> str:
    r = subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else f"failed: {r.stderr.strip()}"
