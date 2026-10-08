"""Rough variable cost per VitaScribe action, from the code and public prices.

Estimates, not measurements: token counts come from the length of the system
prompts in services/cloud_api and assumed input sizes. Prices in USD as found
on 8 October 2026 (see docs/bedrijf/BLAUWDRUK.md for sources). Replace the
assumptions with logged token counts once the server logs them for Mistral.

Run: python3 docs/bedrijf/kostprijsmodel.py
"""
# prices USD
VOX=0.003      # per audio minute (Voxtral Mini Transcribe 2)
DG=0.0058      # Deepgram nova-3 streaming multilingual-ish upper bound
LG=(0.50,1.50); SM=(0.15,0.60); SON=(2.0,10.0); HAI=(1.0,5.0)
VTTS=16/1e6    # per output char
C=3.5          # chars per token (Dutch, rough)
def llm(p,inch,outtok): return inch/C*p[0]/1e6 + outtok*p[1]/1e6
USD2EUR=0.87
rec=8  # minutes recorded per consult
tr=rec*800 # transcript chars (~120 words/min * ~6.5 chars)
eu = {
 'stt consult':(rec+7.5)*VOX,
 'soep':llm(LG,5191+tr,1000),
 'controleronde':llm(LG,2264+tr+3000,400),
 'nazorg':llm(SM,1242+3000,400),
}
cl = {
 'stt deepgram':rec*DG,
 'vraagsuggesties':sum(llm(HAI,1342+min(i*800/2*1,tr)+200,300) for i in range(int(rec*2))),
 'soep':llm(SON,5191+tr,1000),
 'nazorg':llm(HAI,1242+3000,400),
}
print('EU consult', {k:round(v,4) for k,v in eu.items()}, 'tot $',round(sum(eu.values()),4))
print('Claude consult', {k:round(v,4) for k,v in cl.items()}, 'tot $',round(sum(cl.values()),4))
dossier=30000
acts = {
 'brief (dossier 30k tekens)':(llm(LG,2000+dossier,1500),llm(SON,2000+dossier,1500)),
 'brief (dossier max 160k)':(llm(LG,2000+160000,1500),llm(SON,2000+160000,1500)),
 'dossiervraag':(llm(LG,2531+dossier,600),llm(SON,2531+dossier,600)),
 'klinisch meedenken':(llm(LG,1900+8000,600),llm(SON,1900+8000,600)),
 'e-consult':(llm(LG,2845+dossier+3000,1500),llm(SON,2845+dossier+3000,1500)),
 'post/specialistenbrief':(llm(LG,3200+15000,800),llm(SON,3200+15000,800)),
 'dicteren 2 min':(2*VOX+llm(SM,1500+1600,400),2*DG+llm(HAI,1500+1600,400)),
}
for k,(a,b) in acts.items(): print(f'{k}: EU ${a:.4f}  Claude ${b:.4f}')
turns=40
tolk = 15*VOX + turns*llm(SM,1600+300,150) + turns*150*VTTS
print('tolk 15 min $',round(tolk,4), 'waarvan TTS', round(turns*150*VTTS,4))
# monthly per arts
n_cons=400
mix = {'brief (dossier 30k tekens)':40,'dossiervraag':40,'klinisch meedenken':20,'e-consult':20,'post/specialistenbrief':40,'dicteren 2 min':40}
eu_m = n_cons*sum(eu.values()) + sum(acts[k][0]*v for k,v in mix.items()) + 4*tolk
cl_m = n_cons*sum(cl.values()) + sum(acts[k][1]*v for k,v in mix.items()) + 4*tolk
print('per arts per maand EU $',round(eu_m,2),'€',round(eu_m*USD2EUR,2),' consult-aandeel',round(n_cons*sum(eu.values())/eu_m,2))
print('per arts per maand Claude $',round(cl_m,2),'€',round(cl_m*USD2EUR,2))
print('extras EU $',round(sum(acts[k][0]*v for k,v in mix.items())+4*tolk,2))
print('controles aandeel STT', round(7.5/(rec+7.5),2))
