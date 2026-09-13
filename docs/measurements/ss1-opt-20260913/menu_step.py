import fcntl, json, os, struct, sys, time
from pathlib import Path
steps=json.loads(sys.argv[1])
fd=os.open('/dev/uinput',os.O_WRONLY|os.O_NONBLOCK)
fcntl.ioctl(fd,0x40045564,1)
for code in range(1,256): fcntl.ioctl(fd,0x40045565,code)
os.write(fd,struct.pack('80sHHHHI',b'SS1 performance validation keyboard',3,0x1209,0x5341,1,0)+bytes(1024))
fcntl.ioctl(fd,0x5501)
def event(kind,code,value): os.write(fd,struct.pack('llHHi',0,0,kind,code,value))
try:
 time.sleep(3)
 for step in steps:
  if isinstance(step,int):
   event(1,step,1);event(0,0,0);time.sleep(.15)
   event(1,step,0);event(0,0,0);time.sleep(1.1)
  else:
   before=set(Path('/media/fat/screenshots').rglob('*.png'))
   Path('/dev/MiSTer_cmd').write_text('screenshot\n');time.sleep(2)
   after=set(Path('/media/fat/screenshots').rglob('*.png'))
   print(json.dumps({'label':step,'paths':[str(p) for p in sorted(after-before)]}),flush=True)
finally:
 fcntl.ioctl(fd,0x5502);os.close(fd)
