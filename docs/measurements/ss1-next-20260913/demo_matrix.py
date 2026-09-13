import os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
doom=Path('/home/alberto/Repos/Doom/build/ss1-next-20260913')
env=dict(os.environ,SSH_ASKPASS=str(root/'askpass.sh'),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0')
while not (root/'batch-profile-rotate-sigil2/metadata.json').exists(): time.sleep(5)
for build in sys.argv[1:]:
 subprocess.run(['scp','-O','-q',str(doom/build/'.obj/doom/app.elf'),'root@192.168.1.245:/media/fat/.openfpgaOS-profile-20260913/profile.elf'],env=env,check=True)
 for game,name in [('SIGIL','sigil1'),('SIGILII','sigil2')]:
  run=build+'-'+name
  with (root/(run+'.log')).open('w') as log:
   subprocess.run([sys.executable,str(root/'run.py'),run,game,'counter','-noperf','-perfdemo'],stdout=log,stderr=subprocess.STDOUT,check=True)
  print((root/(run+'.log')).read_text().splitlines()[-1],flush=True)
