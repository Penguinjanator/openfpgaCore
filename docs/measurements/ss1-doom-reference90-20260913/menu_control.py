import json, os, shlex, subprocess, sys
from pathlib import Path
here=Path(__file__).resolve().parent
env=dict(os.environ,SSH_ASKPASS=str(here/'askpass.sh'),SSH_ASKPASS_REQUIRE='force',DISPLAY=':0')
subprocess.run(['scp','-O','-q',str(here/'menu_step.py'),'root@192.168.1.245:/tmp/ss1_menu_step.py'],env=env,check=True)
steps=json.loads(sys.argv[1])
result=subprocess.check_output(['ssh','-n','-o','LogLevel=ERROR','-o','ConnectTimeout=6','root@192.168.1.245','python3 /tmp/ss1_menu_step.py '+shlex.quote(json.dumps(steps))],env=env).decode()
print(result,flush=True)
with (here/'menu-verified.jsonl').open('a') as out: out.write(result)
folder=here/'menu-screenshots';folder.mkdir(exist_ok=True)
for line in result.splitlines():
 row=json.loads(line)
 for path in row['paths']:
  subprocess.run(['scp','-O','-q','root@192.168.1.245:'+path,str(folder/(row['label']+'.png'))],env=env,check=True)
