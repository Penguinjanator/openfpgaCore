from pathlib import Path
from elftools.elf.elffile import ELFFile
import subprocess,struct,json,sys
out=Path(__file__).resolve().parent
root=out.parents[1];sm=root.parent/'SM64/src/sm64';sdk=root.parent/'openfpgaSDK/src/sdk'
original=root.parent/'SM64/.obj/sm64/app.elf'
def symbols(p):
 with p.open('rb') as f:
  e=ELFFile(f);return {s.name:dict(addr=s['st_value'],size=s['st_size'],kind=s['st_info']['type'],bind=s['st_info']['bind'],section=s['st_shndx']) for s in e.get_section_by_name('.symtab').iter_symbols() if s.name}
orig=symbols(original)
def build(label,sources,forward,data_forward=(),bind=('gfx_vc_true',)):
 d=out/'overlays'/label;d.mkdir(parents=True,exist_ok=True)
 flags=['clang','--target=riscv32-unknown-elf','-march=rv32imafc_zicsr_zifencei','-mabi=ilp32f','-O3','-ffast-math','-ffp-contract=off','-fcommon','-fno-strict-aliasing','-fwrapv','-ffunction-sections','-fdata-sections','-nostdinc','-isystem',str(sdk/'musl/include'),'-I'+str(sdk/'include'),'-I'+str(sm),'-I'+str(sm/'sm64/include'),'-I'+str(sm/'sm64/src'),'-I'+str(sm/'sm64/src/pc'),'-I'+str(sm/'sm64'),'-I'+str(sm/'sm64/build/us_pc'),'-I'+str(sm/'sm64/build/us_pc/include'),'-DSM64_PROFILE=0','-DVERSION_US','-DNON_MATCHING','-DAVOID_UB','-D_LANGUAGE_C','-DF3DEX_GBI_2E','-DNO_SEGMENTED_MEMORY','-DWIDESCREEN=0','-DENABLE_SOFTRAST','-DTARGET_OPENFPGA','-Wno-implicit-function-declaration']
 if label=='accurate_math':flags+=['-fno-associative-math']
 objs=[]
 for name,source in sources.items():
  p=d/name;p.write_text(source);o=p.with_suffix('.o');objs.append(o)
  subprocess.run([*flags,'-I'+str(sm/'sm64/src/pc/gfx'),'-c',str(p),'-o',str(o)],check=True)
 allsyms=[(k,v) for o in objs for k,v in symbols(o).items()];syms=dict(allsyms);defined={k for k,v in allsyms if v['section']!='SHN_UNDEF'}
 imports={k for k,v in syms.items() if v['section']=='SHN_UNDEF'}-defined
 imports.update(k for k in bind if k in syms)
 missing=imports-orig.keys();assert not missing,missing
 script='SECTIONS { . = 0x13c00000; .text : { *(.text*) } .rodata : { *(.srodata*) *(.rodata*) } .data : { *(.sdata*) *(.data*) } .bss : { *(.sbss*) *(.bss*) *(COMMON) } /DISCARD/ : { *(.comment) *(.riscv.attributes) } }\n'
 # Absolute assignments before section placement resolve COMMON/shared globals.
 script='\n'.join(f'{k} = 0x{orig[k]["addr"]:x};' for k in sorted(imports))+'\n'+script
 (d/'overlay.ld').write_text(script)
 subprocess.run(['/opt/rocm/lib/llvm/bin/lld','-flavor','gnu','-m','elf32lriscv','--no-relax','-T',str(d/'overlay.ld'),'-o',str(d/'overlay.elf'),*map(str,objs)],check=True)
 new=symbols(d/'overlay.elf');words={}
 with (d/'overlay.elf').open('rb') as f:
  e=ELFFile(f)
  for seg in e.iter_segments():
   if seg['p_type']!='PT_LOAD':continue
   a=seg['p_paddr'];n=seg['p_memsz'];assert 0x13c00000<=a and a+n<0x13f00000
   b=seg.data()+bytes(n-seg['p_filesz']);b+=bytes((-len(b))%4)
   for i in range(0,len(b),4):words[a+i]=int.from_bytes(b[i:i+4],'little')
 for oldname,newname in forward.items():
  a=orig[oldname]['addr'];target=new[newname]['addr'];delta=target-a
  hi=(delta+0x800)>>12;lo=delta-(hi<<12)
  assert orig[oldname]['size']>=8
  words[a]=((hi&0xfffff)<<12)|(5<<7)|0x17 # auipc t0
  words[a+4]=((lo&0xfff)<<20)|(5<<15)|0x67 # jalr zero,t0
 for name in data_forward:
  assert orig[name]['size']==new[name]['size'],name
  a=orig[name]['addr'];b=new[name]['addr'];n=orig[name]['size'];assert n%4==0
  for i in range(0,n,4):words[a+i]=words[b+i]
 (d/'patch.words').write_text(''.join(f'{a:08x} {v:08x}\n' for a,v in sorted(words.items())))
 (d/'manifest.json').write_text(json.dumps(dict(forward=forward,data_forward=data_forward,imports=sorted(imports),bytes=4*len(words),compiler=flags),indent=2)+'\n')
 print('built',label,4*len(words),flush=True)
if __name__=='__main__':
 gpu=(sm/'sm64/src/pc/gfx/gfx_gpu.c').read_text()
 wm=(sm/'pocket/wm_pocket.c').read_text()
 exports=['gfx_gpu_boot','gfx_gpu_present','gfx_gpu_vtx_cache_begin','gfx_gpu_vtx_cache_tri','gpu_present_prof_get','gpu_ring_prof_get','gpu_vc_prof_get']
 variant=sys.argv[1]
 if variant in ['backend_clang','res256']:
  if variant=='res256':
   gpu=gpu.replace('#define SCR_W       320','#define SCR_W       256').replace('#define SCR_H       240','#define SCR_H       192')
   wm=wm.replace('#define SCREEN_WIDTH  320','#define SCREEN_WIDTH  256').replace('#define SCREEN_HEIGHT 240','#define SCREEN_HEIGHT 192')
  build(variant,{'gfx_gpu.c':gpu,'wm_pocket.c':wm},{x:x for x in exports if x in orig},['gfx_gpu_api','gfx_pocket_wm_api'])
