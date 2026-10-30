"""Render the saved retrospective confusion matrix; no inference or refitting."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
metrics=json.loads((ROOT/'api/final_evaluation/metrics.json').read_text())['retrospective_third_vial']
matrix=np.array([[metrics['tp'],metrics['fn']],[metrics['fp'],metrics['tn']]])
assert matrix.sum()==metrics['n']==19
plt.rcParams.update({'font.family':'DejaVu Sans','svg.fonttype':'none'})
fig=plt.figure(figsize=(12.8,8),facecolor='white')
ax=fig.add_axes([.19,.22,.43,.57])
ax.imshow(matrix,cmap='Blues',vmin=0,vmax=9)
ax.set_xticks([0,1],['Flagged for review','No deviation flagged'],fontsize=12)
ax.set_yticks([0,1],['Expected carryover','Documented clean'],fontsize=12)
ax.set_xlabel('Predicted appearance finding',fontsize=13,labelpad=12)
ax.set_ylabel('Project-derived label',fontsize=13,labelpad=12)
ax.tick_params(length=0,pad=10)
ax.set_xticks(np.arange(-.5,2,1),minor=True)
ax.set_yticks(np.arange(-.5,2,1),minor=True)
ax.grid(which='minor',color='white',linewidth=5)
ax.tick_params(which='minor',bottom=False,left=False)
for spine in ax.spines.values(): spine.set_visible(False)
labels=[['True positive','False negative'],['False positive','True negative']]
for row in range(2):
    for col in range(2):
        value=matrix[row,col]; color='white' if value>=5 else '#203249'
        ax.text(col,row-.08,str(value),ha='center',va='center',fontsize=38,fontweight='bold',color=color)
        ax.text(col,row+.22,labels[row][col],ha='center',va='center',fontsize=12,color=color)
fig.text(.07,.92,'FlowSight | Carryover inspection',fontsize=23,fontweight='bold',color='#203249')
fig.text(.07,.87,'Retrospective third-vial reference comparison · 19 scored vials',fontsize=14,color='#53647a')
for y,label,value in [( .72,'Accuracy',(metrics['tp']+metrics['tn'])/19),(.62,'Recall',metrics['tp']/(metrics['tp']+metrics['fn'])),(.52,'Precision',metrics['tp']/(metrics['tp']+metrics['fp'])),(.42,'F1 score',2*metrics['tp']/(2*metrics['tp']+metrics['fp']+metrics['fn']))]:
    fig.text(.73,y,label,fontsize=13,color='#53647a')
    fig.text(.73,y-.045,f'{value:.1%}',fontsize=25,fontweight='bold',color='#19617a')
fig.text(.07,.10,'9 expected carryover cases + 10 documented-clean cases. Third-vial references are excluded from scoring.',fontsize=10.5,color='#53647a')
fig.text(.07,.065,'Vial 1 excluded: preceding transition unknown. Uses later fills; not immediate or independent plant-test performance.',fontsize=10.5,color='#53647a')
fig.text(.07,.03,'Labels derive from project_desc.txt. Development results; this evaluates measured color comparisons, not Cosmos explanations.',fontsize=10.5,color='#53647a')
for ext in ('png','svg'):
    path=ROOT/f'docs/confusion-matrix-retrospective.{ext}'
    fig.savefig(path,dpi=200,facecolor='white')
    print(path)
plt.close(fig)
