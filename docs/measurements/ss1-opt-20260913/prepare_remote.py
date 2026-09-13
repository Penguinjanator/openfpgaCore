from pathlib import Path
import re
import sys
sys.path.insert(0, '/tmp')
from ss1_fat import Fat

base = Path('/media/fat/.openfpgaOS-profile-20260913')
fat = Fat(str(base/'saves.vhd'), True)
cfg = fat.get('/Doom/Doom/Doom.cfg').split(b'\0')[0]
cfg = re.sub(rb'(?m)^screenblocks\s+\d+', b'screenblocks                  10', cfg)
for game in ['Doom', 'SIGIL', 'SIGILII']:
    fat.put('/Doom/'+game+'/'+game+'.cfg', cfg)
    for slot in range(5, 10):
        fat.put('/Doom/'+game+'/slot_'+str(slot)+'.sav', b'')
print('Private settings:', '\n'.join(x for x in cfg.decode().splitlines() if any(k in x for k in ['screenblocks','refresh_mode','interpolation','music_volume'])))
boot = Fat(str(base/'boot.vhd'))
for e in boot.directory(boot.lookup('/Doom/COMMON')[1]):
    if any(k in e[0].upper() for k in ['SIGIL', 'DOOMU', 'BANK', 'MUS']): print(e)

game = sys.argv[1] if len(sys.argv)>1 else 'Doom'
args = {'Doom':'-iwad DOOM.WAD -loadgame 0',
        'SIGIL':'-iwad doomu.wad -merge SIGIL_COMPAT_V1_23.wad -warp 3 1 -nomonsters -perfrestart',
        'SIGILII':'-iwad doomu.wad -merge SIGIL_II_V1_0.WAD -warp 6 1 -nomonsters -perfrestart'}[game]
extra = ' '.join(sys.argv[2:])
(base/'profile.ini').write_text('[os]\nGAME=Doom\nINSTANCE='+game+'\nELF=profile.elf\nARGS='+args+' -noautoload -dehlump -config '+game+'.cfg -extraconfig '+game+'.cfg -saveprefix '+game+' -perfrotate -perfcapture yes '+extra+'\n')
(base/'profile.mgl').write_text('''<mistergamedescription>
<rbf>_Computer/OpenfpgaOS</rbf>
<file delay="1" type="s" index="0" path="/media/fat/.openfpgaOS-profile-20260913/boot.vhd"/>
<file delay="2" type="s" index="1" path="/media/fat/.openfpgaOS-profile-20260913/saves.vhd"/>
<file delay="3" type="f" index="2" path="/media/fat/.openfpgaOS-profile-20260913/profile.elf"/>
<file delay="4" type="f" index="1" path="/media/fat/.openfpgaOS-profile-20260913/profile.ini"/>
</mistergamedescription>
''')
print((base/'profile.ini').read_text())
