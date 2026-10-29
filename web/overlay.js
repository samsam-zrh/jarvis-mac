const token=new URLSearchParams(location.hash.slice(1)).get('token')||sessionStorage.getItem('jarvis-token')||'';
if(token){sessionStorage.setItem('jarvis-token',token);history.replaceState(null,'',location.pathname);}
const $=id=>document.getElementById(id);
let taskId='',cursor=0,answer='',lastState='',listening=false,progressDetail='';
const native=(action,value)=>window.webkit?.messageHandlers?.jarvis.postMessage({action,value});
$('expand').onclick=()=>native('expand');$('close').onclick=()=>native('hide');
$('cancel').onclick=()=>fetch('/api/cancel',{method:'POST',headers:{Authorization:'Bearer '+token}});
let resizeTimer;
let notchWidth=179,availableWidth=1000;
function fitPanel(){
 clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{
  const panel=$('panel'),expanded=['speaking','done','error'].includes(document.body.dataset.phase);
  const width=Math.min(availableWidth,Math.max(expanded?420:376,notchWidth+(expanded?240:196)));
  const size={width,height:Math.ceil(panel.getBoundingClientRect().height)};
  native('resize',size);
 },80);
}
let detailMessage='Votre voix reste sur ce Mac';
function setDetail(text){detailMessage=text;const r=$('response');$('detail').textContent=r.scrollHeight-r.clientHeight>4?'Texte complet · défilez pour lire':text;}
function showText(text,follow=true){const response=$('response');const nearEnd=response.scrollHeight-response.scrollTop-response.clientHeight<30;response.textContent=text;if(follow&&nearEnd)response.scrollTop=response.scrollHeight;setDetail(detailMessage);fitPanel();}
new ResizeObserver(fitPanel).observe($('panel'));
$('panel').addEventListener('mouseenter',()=>native('hold',true));
$('panel').addEventListener('mouseleave',()=>native('hold',false));
function phase(value,label){document.body.dataset.phase=value;$('state').textContent=label;$('voice-mark').classList.toggle('active',['listening','working','speaking'].includes(value));fitPanel();}
window.jarvisOverlay={
 configure(layout){notchWidth=Math.max(0,layout.notchWidth||0);availableWidth=Math.max(280,layout.availableWidth||1000);document.documentElement.style.setProperty('--notch-width',notchWidth+'px');document.documentElement.style.setProperty('--notch-height',Math.max(32,layout.notchHeight||32)+'px');document.documentElement.style.setProperty('--response-cap',Math.max(100,layout.responseCap||300)+'px');document.body.classList.toggle('no-notch',!layout.hasNotch);fitPanel();},
 listening(){listening=true;answer='';phase('listening','À l’écoute');showText('Parlez naturellement.');setDetail('Votre voix reste sur ce Mac');},
 transcript(text){if(listening)showText(text||'Parlez naturellement.');},
 thinking(text){listening=true;phase('working','Je m’en occupe');showText(text);setDetail('Vérification de votre demande');},
 idle(){listening=false;phase('idle','En veille');},
 level(value){document.documentElement.style.setProperty('--level',Math.max(.15,Math.min(1,Number(value)||0)));},
 error(text){listening=false;phase('error','À vérifier');showText(text);}
};
async function poll(){
 try{
  const response=await fetch('/api/activity',{headers:{Authorization:'Bearer '+token}});if(!response.ok)return;
  const data=await response.json();
  if(listening&&(data.id||'')===taskId)return;
  if(data.id&&data.id!==taskId){listening=false;taskId=data.id;cursor=0;answer='';progressDetail='';showText(data.request||'Je m’en occupe.');native('show');}
  for(const event of data.events.slice(cursor)){
   if(event.kind==='text'){answer+=event.text;showText(answer);}
   if(event.kind==='tool')setDetail('Action en cours sur votre Mac');
   if(event.kind==='progress'){const done=new Set(event.completed||[]),steps=event.steps||[];const next=steps.find((s,i)=>!done.has(i+1));progressDetail=done.size+'/'+steps.length+' · '+(next?.goal||'Étapes confirmées');}
   if(event.kind==='error')showText(event.text);
  }
  cursor=data.events.length;
  const active=data.status==='running';
  if(data.id){
   phase(data.speaking?'speaking':active?'working':data.status==='error'?'error':'done',data.speaking?'Je vous réponds':active?'En cours':data.status==='completed'?'C’est fait':data.status==='cancelled'?'Arrêté':'À vérifier');
   setDetail(data.speaking?'Redites « Jarvis » pour interrompre':active?(progressDetail||'Action en cours sur votre Mac'):'Dites « Jarvis »');
  }
  $('cancel').hidden=!active&&!data.speaking;
  const state=taskId+':'+data.status+':'+data.speaking;
  if(state!==lastState){lastState=state;native('activity',{busy:active||data.speaking,finished:Boolean(data.id)&&!active&&!data.speaking,readingSeconds:Math.min(90,Math.max(12,answer.length/18))});}
 }catch{}finally{setTimeout(poll,250);}
}
poll();
