import hashlib, json, os, shlex, subprocess, sys, time
from pathlib import Path
here=Path(__file__).resolve().parent
doom=here/'software'
env=dict(os.environ,SSH_ASKPASS=str(here/'askpass.sh'),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0')
def ssh(cmd):
 return subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245',cmd],env=env)
def menu():
 ssh('echo load_core /media/fat/menu.rbf > /dev/MiSTer_cmd')
 for attempt in range(20):
  time.sleep(.5)
  if ssh('cat /tmp/CORENAME').decode().strip()=='MENU':return
 raise RuntimeError('MENU did not load')
subprocess.run(['scp','-O','-q',str(here/'prepare_remote.py'),'root@192.168.1.245:/tmp/ss1_prepare.py'],env=env,check=True)
subprocess.run(['scp','-O','-q',str(here/'fat_access.py'),'root@192.168.1.245:/tmp/ss1_fat.py'],env=env,check=True)
jobs=[]
resume='--resume' in sys.argv[1:]
for name in (a for a in sys.argv[1:] if a!='--resume'):
 # build:core:label:mode, with mode coarse or normal
 build,core,label,mode=name.split(':')
 for game,short in ([('SIGILII','sigil2')] if mode=='coarse' else [('SIGIL','sigil1'),('SIGILII','sigil2')]):
  jobs.append((build,core,label,mode,game,short))
try:
 for build,core,label,mode,game,short in jobs:
  name=label+'-'+short
  complete=here/name/'metadata.json'
  if resume and complete.exists():
   meta=json.loads(complete.read_text())
   digest=hashlib.sha256((doom/build/'.obj/doom/app.elf').read_bytes()).hexdigest()
   assert meta['game']==game and meta['core']==core and meta['hashes'].split()[0]==digest
   assert len(json.loads((here/name/'frames.json').read_text()))==meta['frames']
   print('Verified completed capture',name,flush=True)
   continue
  menu()
  subprocess.run(['scp','-O','-q',str(doom/build/'.obj/doom/app.elf'),'root@192.168.1.245:/media/fat/.openfpgaOS-profile-20260913/profile.elf'],env=env,check=True)
  args=[] if mode=='coarse' else ['-noperf']
  if mode!='rotate':args.append('-perfdemo')
  with (here/(name+'.log')).open('w') as log:
   subprocess.run([sys.executable,str(here/'run.py'),name,game,core,*args],stdout=log,stderr=subprocess.STDOUT,check=True)
  print((here/(name+'.log')).read_text().splitlines()[-1],flush=True)
finally:
 menu()
