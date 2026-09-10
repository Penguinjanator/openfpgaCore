from pathlib import Path
import random, struct, sys
p=Path(sys.argv[1]).resolve()
p.mkdir(parents=True, exist_ok=True)
random.seed(100)
f32=lambda v: struct.unpack('<f',struct.pack('<f',v))[0]
bits=lambda v: struct.unpack('<I',struct.pack('<f',v))[0]
rows=[]
for i in range(1024):
 a=random.randrange(1,0x7fffffff); b=random.randrange(1,0xffff)
 x=f32(random.uniform(-10000,10000)); y=f32(random.uniform(0.1,100))
 z=f32(f32(f32(f32(x+y)*y)-x)/y)
 # These normal finite inputs avoid the configured subnormal-flush behavior.
 rows.append('{'+','.join(hex(n)+'u' for n in (a,b,(a*b+a//b)&0xffffffff,bits(x),bits(y),bits(z),int(x)&0xffffffff))+'}')
(p/'vectors.h').write_text('static const unsigned vectors[1024][7]={\n'+',\n'.join(rows)+'\n};\n')
(p/'firmware.mif').write_text('WIDTH=32;\nDEPTH=8192;\nADDRESS_RADIX=DEC;\nDATA_RADIX=HEX;\nCONTENT BEGIN\n0 : 103202B7;\n1 : 00028067;\n[2..8191] : 00000013;\nEND;\n')

import math
raw=[0,0x80000000,0x7f800000,0xff800000,0x7fc00000,0xffc00000,
     0x7f800001,0xff800001,0x7fffffff,0xffffffff,0x00800000,0x80800000]
for v in [-2**32,-2**31,-2**31+128,-65536.5,-3.5,-2.5,-1.5,-1.0,-0.5,
          -0.25,0.25,0.5,1.0,1.5,2.5,3.5,65536.5,2**31-128,2**31,
          2**32-256,2**32]:
 b=bits(v)
 raw.extend([b-1,b,b+1])
for _ in range(128):
 b=random.getrandbits(32)
 if b&0x7f800000: raw.append(b)
frows=[]
for b in sorted(set(raw)):
 x=struct.unpack('<f',struct.pack('<I',b))[0]
 for rm in range(5):
  if math.isfinite(x):
   rounded=[lambda x:round(x),math.trunc,math.floor,math.ceil,
            lambda x:math.copysign(math.floor(abs(x)+0.5),x)][rm](x)
  for unsigned in [0,1]:
   lo=0 if unsigned else -2**31; hi=2**32-1 if unsigned else 2**31-1
   if math.isnan(x): result=hi; flags=16
   elif math.isinf(x): result=lo if x<0 else hi; flags=16
   elif rounded<lo: result=lo; flags=16
   elif rounded>hi: result=hi; flags=16
   else: result=int(rounded); flags=int(rounded!=x)
   frows.append('{'+','.join(hex(n&0xffffffff)+'u' for n in (b,rm,unsigned,result,flags))+'}')
(p/'f2i_vectors.h').write_text('static const unsigned f2i_vectors[][5]={\n'+',\n'.join(frows)+'\n};\n')
