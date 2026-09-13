import os, shlex, subprocess, time
from pathlib import Path
here=Path(__file__).resolve().parent
base='/media/fat/.openfpgaOS-release-20260913'
previous='/media/fat/.openfpgaOS-profile-20260913'
env=dict(os.environ,SSH_ASKPASS=str(here/'askpass.sh'),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0')
def ssh(cmd,timeout=40):
 return subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245',cmd],env=env,timeout=timeout)
def remote(script):return ssh('python3 -u -c '+shlex.quote(script))
def scp(source,target):
 subprocess.run(['scp','-O','-q',str(source),'root@192.168.1.245:'+target],env=env,check=True,timeout=40)
def menu():
 ssh('echo load_core /media/fat/menu.rbf > /dev/MiSTer_cmd')
 for _ in range(30):
  time.sleep(.5)
  if ssh('cat /tmp/CORENAME').strip()==b'MENU':return
 raise RuntimeError('MENU did not load')
