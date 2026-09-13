"""Temporary keyboard for an SS1 menu smoke test; run only after benchmarks."""
import fcntl, os, struct, subprocess, time
from pathlib import Path
base = Path('/media/fat/.openfpgaOS-profile-20260913')
log = (base/'menu-keys.log').open('w', buffering=1)
fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
fcntl.ioctl(fd, 0x40045564, 1)  # EV_KEY
for key in range(1, 256): fcntl.ioctl(fd, 0x40045565, key)
name = b'SS1 performance validation keyboard'
os.write(fd, struct.pack('80sHHHHI',name,3,0x1209,0x5341,1,0)+bytes(1024))
fcntl.ioctl(fd, 0x5501)
def event(kind, code, value):
 os.write(fd, struct.pack('llHHi',0,0,kind,code,value))
def key(code):
 event(1,code,1);event(0,0,0);time.sleep(.1)
 event(1,code,0);event(0,0,0);time.sleep(.25)
def capture(label):
 print(time.time(),label,file=log)
 Path('/dev/MiSTer_cmd').write_text('screenshot\n')
 time.sleep(2)
try:
 time.sleep(3)
 capture('gameplay before menus')
 key(88)  # F12: MiSTer OSD
 time.sleep(2)
 capture('MiSTer OSD requested')
 for _ in range(6): key(108);key(103)
 key(88)
 time.sleep(2)
 key(1)  # Escape: Doom menu
 capture('Doom main menu requested')
 key(108);key(28)  # Options
 capture('Doom options requested')
 for _ in range(6): key(108);key(103)
 key(1);key(1)
 capture('gameplay after Doom options')
 for i in range(20):
  key(88);time.sleep(.2);key(108);key(103);key(88);time.sleep(.2)
  print(time.time(),'OSD cycle',i+1,file=log)
 capture('gameplay after repeated OSD navigation')
 for code in (23,32,48,18,35,24,38,32,47): key(code)  # idbeholdv
 capture('standard invulnerability lighting requested')
 time.sleep(20)
 capture('gameplay after invulnerability')
finally:
 for code in (1,28,88,103,108): event(1,code,0)
 event(0,0,0)
 fcntl.ioctl(fd,0x5502);os.close(fd);log.close()
