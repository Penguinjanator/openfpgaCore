from pathlib import Path
import json, statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
out=root/'figures';out.mkdir(exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig, axes=plt.subplots(1,2,figsize=(10,3.7),sharey=True,layout='constrained')
for ax, game, title in zip(axes,('sigil1','sigil2'),('SIGIL 1 opening','SIGIL 2 opening')):
 for prefix,label,color in [('baseline-control','Before','#8a939d'),('final2-control','After','#007a9c')]:
  rows=json.loads((root/(prefix+'-'+game)/'frames.json').read_text())
  bins={}
  for r in rows:bins.setdefault(r[6]>>27,[]).append(r[58]/1000)
  xs=sorted(bins)
  ax.plot([(x+.5)*360/32 for x in xs],[statistics.mean(bins[x]) for x in xs],label=label,color=color,lw=2)
 ax.axhline(1000/60,color='#b76720',ls='--',lw=1,label='16.67 ms')
 ax.set(title=title,xlabel='Viewing direction (degrees)',xlim=(0,360));ax.grid(axis='y',alpha=.2)
axes[0].set_ylabel('Mean frame preparation (ms)');axes[1].legend(frameon=False)
fig.suptitle('SS1 at 100 MHz · music on · coarse probes disabled')
for ext in ('png','svg','pdf'):fig.savefig(out/('preparation-by-heading.'+ext),dpi=180)
plt.close(fig)
