import json
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
summaries = json.loads((root/'summaries.json').read_text())
groups = {
    'before': ['before', 'before-repeat'],
    'full': ['skip', 'skip-repeat'],
    'walls': ['walls'],
    'rotation-before': ['rotate-before', 'rotate-before-repeat'],
    'rotation-full': ['rotate-software', 'rotate-software-repeat'],
    'rotation-walls': ['rotate-walls'],
}
result = {}
for game in ('sigil1', 'sigil2'):
    result[game] = {}
    for label, names in groups.items():
        names = [n+'-'+game for n in names if n+'-'+game in summaries]
        if not names:
            continue
        values = [summaries[n] for n in names]
        result[game][label] = dict(
            captures=names,
            fps=st.mean(v['fps'] for v in values),
            prepare_ms=st.mean(v['mean_ms']['prepare'] for v in values),
            prepare_p95_ms=st.mean(v['prepare_p95_ms'] for v in values),
            angle_balanced_prepare_ms=st.mean(v['angle_balanced_prepare_ms'] for v in values))
(root/'final-comparison.json').write_text(json.dumps(result, indent=2)+'\n')

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
for ax, game in zip(axes, ('sigil1', 'sigil2')):
    for label, caption in [('rotation-before', 'Before'),
                           ('rotation-full', 'Full candidate'),
                           ('rotation-walls', 'Masked walls only')]:
        item = result[game].get(label)
        if item is None:
            continue
        per_run = []
        for name in item['captures']:
            rows = json.loads((root/name/'frames.json').read_text())
            per_run.append([st.mean(r[58]/1000 for r in rows if r[6] >> 27 == i)
                            for i in range(32)])
        values = [st.mean(v[i] for v in per_run) for i in range(32)]
        count = len(per_run)
        ax.plot([(i+.5)*360/32 for i in range(32)], values,
                label=f'{caption} ({count} {"run" if count == 1 else "runs"})')
    ax.axhline(1000/60, color='gray', linestyle='--', label='60 Hz frame budget')
    ax.set_title('SIGIL I opening' if game == 'sigil1' else 'SIGIL II opening')
    ax.set_xlabel('Viewing direction (degrees)')
    ax.set_xlim(0, 360)
    ax.grid(alpha=.2)
axes[0].set_ylabel('Mean preparation time (ms)')
axes[1].legend(fontsize=8)
fig.suptitle('SS1 at 100 MHz · stationary rotation · instrumented builds')
fig.tight_layout()
fig.savefig(root/'preparation-by-heading.png', dpi=170)
print(json.dumps(result, indent=2))
