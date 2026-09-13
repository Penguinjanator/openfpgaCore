from pathlib import Path
import json
import statistics as st
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
out = root / 'figures'
out.mkdir(exist_ok=True)
plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(3, 1, figsize=(9, 9), sharex=True, layout='constrained')
for ax, game, title in zip(axes, ['doom','sigil1','sigil2'], ['Doom E1M1 saved position','SIGIL 1 opening, E3M1','SIGIL 2 opening, E6M1']):
    for core, color, label in [('old','#747b85','Published GPU'),('new','#147d92','Latest GPU')]:
        rows = json.loads((root/f'v2-{core}-{game}/frames.json').read_text())
        bins = {}
        for r in rows: bins.setdefault(r[6]>>27, []).append(r[58]/1000)
        keys = sorted(bins)
        ax.plot([(k+.5)*360/32 for k in keys], [st.mean(bins[k]) for k in keys], color=color, label=label, linewidth=1.8)
    ax.axhline(16.667, color='#bf5041', linestyle='--', linewidth=1, label='60 FPS preparation budget')
    ax.set_title(title, loc='left', fontweight='bold')
    ax.set_ylabel('Preparation time (ms)')
    ax.grid(axis='y', alpha=.2)
    ax.set_ylim(bottom=0)
axes[0].legend(loc='lower center', ncol=3, frameon=False, fontsize=9)
axes[-1].set_xlabel('View heading (degrees; 32 bins averaged equally)')
axes[-1].set_xlim(0,360)
fig.suptitle('SS1 at 100 MHz · 320×168 viewport · music on\n30-second fixed-position rotations, coarse timing probes enabled', fontsize=13, fontweight='bold')
for suffix in ['png','svg','pdf']: fig.savefig(out/f'preparation-by-heading.{suffix}', dpi=160)
plt.close(fig)

fig, ax = plt.subplots(figsize=(9,4), layout='constrained')
labels=[]
bottom=[0.]*6
groups=[]
for game, title in [('doom','Doom'),('sigil1','SIGIL 1'),('sigil2','SIGIL 2')]:
    for core in ['old','new']:
        s=json.loads((root/f'v2-{core}-{game}/summary.json').read_text())['mean_ms']
        groups.append([s['bsp'],s['planes'],s['masked'],s['prepare']-s['bsp']-s['planes']-s['masked']])
        labels.append(title+'\n'+('Published' if core=='old' else 'Latest'))
for i,(name,color) in enumerate(zip(['BSP / walls','Floors / ceilings','Masked / sprites','Other preparation'],['#155e75','#38a6ae','#83c5be','#bac3c9'])):
    vals=[g[i] for g in groups]
    ax.bar(range(6),vals,bottom=bottom,label=name,color=color,width=.7)
    bottom=[a+b for a,b in zip(bottom,vals)]
ax.axhline(16.667,color='#bf5041',linestyle='--',linewidth=1)
ax.set_xticks(range(6),labels)
ax.set_ylabel('Mean preparation time (ms)')
ax.set_title('CPU renderer stages remain the largest costs',loc='left',fontweight='bold')
ax.legend(ncol=2,frameon=False,loc='upper left')
ax.grid(axis='y',alpha=.15)
ax.set_ylim(0,max(bottom)*1.3)
for suffix in ['png','svg','pdf']: fig.savefig(out/f'renderer-stages.{suffix}',dpi=160)
