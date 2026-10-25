"""Render real calculated household charts; optional matplotlib only, no image AI."""
import json
from pathlib import Path

from .household_report import ROOT, main as generate_tables


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import LogNorm
    generate_tables()
    rows=json.loads((ROOT/'results/household/memory_scenarios.json').read_text())
    comm=json.loads((ROOT/'results/household/communication_scenarios.json').read_text())
    out=ROOT/'figures';out.mkdir(exist_ok=True)
    plt.rcParams.update({'svg.hashsalt':'consent-compute-mesh-household-v1','font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False,
                         'axes.labelcolor':'#253247','text.color':'#13243a','xtick.color':'#34465d','ytick.color':'#34465d',
                         'axes.titleweight':'bold','figure.facecolor':'#f7f9fc','axes.facecolor':'#f7f9fc','savefig.facecolor':'#f7f9fc'})
    def save(fig,name):
        fig.savefig(out/f'{name}.png',dpi=170,bbox_inches='tight')
        fig.savefig(out/f'{name}.svg',bbox_inches='tight',metadata={'Date':None})
        plt.close(fig)
    selected=[r for r in rows if r['household_available_gib_assumed']==12 and r['nominal_weight_bits']==4]
    fig,ax=plt.subplots(figsize=(12,7.5))
    fig.subplots_adjust(left=.1,right=.97,top=.76,bottom=.21)
    fig.text(.1,.95,'What could a fully consenting household mesh hold?',size=20,weight='bold')
    fig.text(.1,.895,'405B parameters: at least 16 hypothetical homes for ideal 4-bit weights',size=15,color='#006b70')
    fig.text(.1,.85,'All bars: nominal 4-bit weights • assumed 12 GiB per home • capacity only, NOT an inference-speed forecast',size=11)
    x=np.arange(3)
    a=ax.bar(x-.19,[r['weight_only_household_lower_bound'] for r in selected],width=.36,color='#087e8b',label='Ideal weight-only lower bound')
    b=ax.bar(x+.19,[r['illustrative_envelope_households'] for r in selected],width=.36,color='#e5a642',label='Illustrative overhead + KV + workspace envelope')
    ax.bar_label(a,padding=5,size=14,weight='bold');ax.bar_label(b,padding=5,size=14,weight='bold')
    ax.set_xticks(x,['8B','70B','405B']);ax.set_xlabel('Representative Llama 3.1 dense model size (not a current-SOTA claim)')
    ax.set_ylabel('Hypothetical households');ax.set_ylim(0,24);ax.set_yticks(range(0,25,4));ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
    ax.legend(loc='upper left',frameon=False,fontsize=10)
    fig.text(.1,.115,'Envelope: +20% weight overhead (assumed), 8,192-token FP16 KV cache, +2 GiB aggregate workspace.',size=10)
    fig.text(.1,.078,'Neither bar establishes accessible kernels, adequate per-device shards, duty cycle or useful throughput.',size=10)
    fig.text(.1,.035,'Source: Meta, The Llama 3 Herd of Models, Table 3 • https://arxiv.org/abs/2407.21783',size=9,color='#526277')
    save(fig,'household_memory_headline')

    fig,axes=plt.subplots(2,1,figsize=(14,9))
    fig.subplots_adjust(left=.12,right=.85,top=.83,bottom=.15,hspace=.52)
    fig.text(.12,.96,'Capacity sensitivity: changing precision and memory changes the count',size=19,weight='bold')
    fig.text(.12,.91,'All households fully consented • budgets are scenarios, not measured US household averages',size=12)
    combinations=[(budget,bits) for budget in [4,12,24] for bits in [4,8,16]]
    fields=[('weight_only_household_lower_bound','Ideal weight-only lower bound'),('illustrative_envelope_households','Envelope: +20% weights + FP16 KV (8,192 tokens, batch 1) + 2 GiB workspace')]
    maximum=max(r['illustrative_envelope_households'] for r in rows)
    norm=LogNorm(vmin=1,vmax=maximum)
    for ax,(field,title) in zip(axes,fields):
        matrix=np.array([[next(r[field] for r in rows if r['parameters_billion_rounded']==p and r['household_available_gib_assumed']==budget and r['nominal_weight_bits']==bits) for budget,bits in combinations] for p in [8,70,405]])
        im=ax.imshow(matrix,cmap='viridis',norm=norm,aspect='auto')
        ax.set_xticks(range(9),[f'{budget} GiB\n{bits}-bit' for budget,bits in combinations],size=10)
        ax.set_yticks(range(3),['8B','70B','405B']);ax.set_title(title,loc='left',size=13,pad=12)
        for (y,x),value in np.ndenumerate(matrix):
            ax.text(x,y,str(value),ha='center',va='center',size=15,weight='bold',color='white' if norm(value)<.55 else '#112337')
        for v in [2.5,5.5]:ax.axvline(v,color='white',lw=3)
    cax=fig.add_axes([.88,.25,.018,.47]);bar=fig.colorbar(im,cax=cax);bar.set_label('Household count (log color scale)')
    bar.set_ticks([1,2,4,8,16,32,64,128,maximum]);bar.set_ticklabels([1,2,4,8,16,32,64,128,maximum])
    fig.text(.12,.085,'Nominal bits/weight are idealized. Actual mixed quantization, scale metadata, runtime allocation and shard constraints differ.',size=10)
    fig.text(.12,.045,'Source: Meta Llama 3 Table 3 + explicit scenario arithmetic. Full assumptions and citations: HOUSEHOLD_ATLAS.md',size=10,color='#526277')
    save(fig,'household_capacity_sensitivity')

    fig,ax=plt.subplots(figsize=(12,8))
    fig.subplots_adjust(left=.12,right=.96,top=.79,bottom=.23)
    fig.text(.12,.95,'More homes can add memory while making interactive decoding harder',size=18,weight='bold')
    fig.text(.12,.90,'Single-sequence decode ceiling • ideal serial layer pipeline • FP16 hidden state width 8,192',size=11)
    fig.text(.12,.855,'Every compute cost is omitted. These curves are NOT predicted or measured inference throughput.',size=11,weight='bold',color='#9a4f00')
    labels=['100 Mbps / 5 ms','20 Mbps / 20 ms','5 Mbps / 50 ms']
    for label,color in zip(labels,['#087e8b','#5974bd','#d08226']):
        points=[r for r in comm if r['link_scenario']==label]
        ax.plot([r['households'] for r in points],[r['decode_tokens_per_second_ceiling_from_communication_only'] for r in points],lw=3,label=label,color=color)
    ax.set_yscale('log');ax.set_xlim(2,64);ax.set_xticks([2,4,8,16,32,48,64]);ax.set_xlabel('Households in one serial layer pipeline (one stage per home)')
    ax.set_ylabel('Tokens/s ceiling from communication alone');ax.grid(alpha=.17,which='both');ax.legend(title='Assumed payload rate / one-way latency per boundary',fontsize=10,title_fontsize=10,frameon=False)
    fig.text(.12,.135,'Formula: 1 / [(H − 1) × (one-way latency + activation bytes / payload bandwidth)]. H=1 has no interhome bound.',size=10)
    fig.text(.12,.095,'Assumptions omit compute, intra-home transfers, serialization, token return, jitter and losses; other parallel layouts differ.',size=10)
    fig.text(.12,.05,'Hidden-size source: https://arxiv.org/abs/2407.21783 • link settings are hypothetical, not US broadband averages.',size=9,color='#526277')
    save(fig,'household_communication_sensitivity')
    print('Rendered 3 calculated charts as PNG and SVG.')


if __name__=='__main__':
    main()
