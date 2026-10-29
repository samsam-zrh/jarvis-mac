const $ = id => document.getElementById(id);
let token = new URLSearchParams(location.hash.slice(1)).get('token') || sessionStorage.getItem('jarvis-token') || '';
if(token){sessionStorage.setItem('jarvis-token',token);history.replaceState(null,'',location.pathname);}
let busy=false, recording=false, currentTask=null, currentMessage=null, config={}, streamAbort=null;
const labels={open_service:'Ouverture du service',find_contacts:'Recherche du contact',draft_message:'Préparation du brouillon',send_message:'Envoi du message',control_media:'Contrôle de la musique',set_audio:'Réglage du son',browser_tabs:'Lecture des onglets',read_browser_tab:'Lecture de la page',task_progress:'Suivi des étapes',use_workspace:'Outils de messagerie',weather_forecast:'Prévisions météo',open_document:'Ouverture du document',search_spotify:'Recherche Spotify',play_spotify:'Lecture Spotify',search_web:'Recherche sur Internet',read_webpage:'Lecture d’une source',create_document:'Création du document',read_document:'Lecture du document',find_files:'Recherche de fichiers',open_item:'Ouverture sur le Mac',shell:'Action sur le Mac',text_editor:'Modification d’un fichier'};
async function api(path,options={}){
  const response=await fetch('/api/'+path,{...options,headers:{Authorization:'Bearer '+token,...(options.body instanceof Blob?{}:{'Content-Type':'application/json'}),...options.headers}});
  if(!response.ok){let message;try{message=(await response.json()).detail;}catch{message='Connexion interrompue';}throw Error(typeof message==='string'?message:JSON.stringify(message));}
  return response;
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,4500);}
function showConversation(){$('welcome').hidden=true;$('conversation').classList.add('visible');}
function renderText(body,text){
  body.replaceChildren();let cursor=0;
  for(const match of text.matchAll(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g)){
    body.append(document.createTextNode(text.slice(cursor,match.index)));
    const link=document.createElement('a');link.textContent=match[1];link.href=match[2];link.rel='noreferrer';body.append(link);cursor=match.index+match[0].length;
  }
  body.append(document.createTextNode(text.slice(cursor)));
}
function message(role,text='',animate=true){
  showConversation();const block=document.createElement('article');block.className='message '+role+(animate?'':' restored');
  if(role==='assistant'){const label=document.createElement('div');label.className='message-label';label.textContent='◈ Jarvis';block.append(label);}
  const body=document.createElement('div');body.className='message-body';renderText(body,text);block.append(body);$('conversation').append(block);scroll();return body;
}
let followConversation=true;
$('conversation').addEventListener('scroll',()=>{const c=$('conversation');followConversation=c.scrollHeight-c.scrollTop-c.clientHeight<70;},{passive:true});
function scroll(){const c=$('conversation');if(followConversation)c.scrollTop=c.scrollHeight;}
function setBusy(value){busy=value;$('send').hidden=value;$('stop').hidden=!value;$('orb').classList.toggle('active',value||recording);$('activity').hidden=!value&&!$('activity-list').children.length;$('send').disabled=value;}
function addActivity(event){
  const entry=document.createElement('div');entry.className='activity-entry';
  const name=(event.name||'').split('__').pop();entry.textContent=labels[name]||name.replaceAll('_',' ');
  const detail=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent='Détails';pre.textContent=JSON.stringify(event.arguments||event.result,null,2);detail.append(summary,pre);entry.append(detail);$('activity-list').append(entry);$('activity-label').textContent=entry.firstChild.textContent;
}
function showProgress(event){
  let entry=$('task-progress');if(!entry){entry=document.createElement('div');entry.id='task-progress';entry.className='activity-entry';$('activity-list').append(entry);}
  entry.replaceChildren();const steps=event.steps||[],done=new Set(event.completed||[]);
  for(const [i,step] of steps.entries()){const row=document.createElement('div');row.textContent=(done.has(i+1)?'✓ ':'○ ')+(typeof step==='string'?step:step.goal);entry.append(row);}
  $('activity-label').textContent=done.size+' / '+steps.length+' étapes confirmées';
}
async function refresh(){
  try{const data=await(await api('status')).json();config=data.settings;$('profile-button').firstChild.textContent=(config.profile==='fast'?'Rapide':'Précis')+' ';$('profile-select').value=config.profile;$('speak-toggle').checked=config.speak;$('desktop-toggle').checked=config.desktop;
    const model=config.models[config.profile];$('status-pill').classList.toggle('ready',data.ready);$('status-pill').lastChild.textContent=data.ready?' Local prêt':data.ollama?' Modèle en préparation':' Moteur en démarrage';
    $('model-note').textContent=model.replace('qwen3.5:','Qwen 3.5 ').replace('-q4_K_M','')+' · Sur votre Mac';
    $('connection-error').hidden=data.ready;$('connection-error').textContent='Le modèle local se prépare. Vous pourrez envoyer votre demande dès qu’il sera prêt.';
    $('permissions-title').textContent=data.desktop_ready?'Accès aux applications prêt':'Accès aux applications à autoriser';
  }catch(e){$('status-pill').lastChild.textContent=' Connexion…';$('connection-error').hidden=false;$('connection-error').textContent=token?'Le moteur démarre. Cette fenêtre se reconnecte automatiquement.':'Ouvrez Jarvis depuis son application Mac pour établir la connexion locale.';}
}
async function send(text){
  if(busy||!text.trim())return;
  const prompt=text.trim();followConversation=true;$('prompt').value='';$('prompt').style.height='auto';setBusy(true);$('activity-list').replaceChildren();$('activity').hidden=false;$('activity-label').textContent='Je m’en occupe…';
  try{
    const task=await(await api('chat',{method:'POST',body:JSON.stringify({text:prompt})})).json();currentTask=task.id;message('user',prompt);currentMessage=message('assistant');
    streamAbort=new AbortController();const response=await api('tasks/'+task.id+'/events',{signal:streamAbort.signal});const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    while(true){const{done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let newline;
      while((newline=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);if(!line)continue;const event=JSON.parse(line);
        if(event.kind==='text'){currentMessage.dataset.raw=(currentMessage.dataset.raw||'')+event.text;renderText(currentMessage,currentMessage.dataset.raw);scroll();}
        if(event.kind==='tool')addActivity(event);
        if(event.kind==='progress')showProgress(event);
        if(event.kind==='status')$('activity-label').textContent=event.text;
        if(event.kind==='error'){message('error',event.text);$('activity-label').textContent='Une étape a échoué';}
        if(event.kind==='done'){$('activity-label').textContent=event.status==='completed'?'Terminé'+(event.elapsed?' en '+event.elapsed+' s':''):event.status==='cancelled'?'Tâche arrêtée':'Tâche interrompue';if(event.status==='cancelled')message('assistant','Tâche arrêtée.');}
      }
    }
  }catch(e){if(e.name!=='AbortError')message('error',e.message);}
  finally{setBusy(false);currentTask=null;streamAbort=null;refresh();}
}
$('composer').addEventListener('submit',e=>{e.preventDefault();send($('prompt').value);});
$('prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send($('prompt').value);}});
$('prompt').addEventListener('input',()=>{$('prompt').style.height='auto';$('prompt').style.height=Math.min($('prompt').scrollHeight,Math.min(240,innerHeight*.32))+'px';});
document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>send(button.dataset.prompt)));
$('stop').addEventListener('click',async()=>{try{await api('cancel',{method:'POST'});}catch(e){toast(e.message);}});
$('activity-toggle').addEventListener('click',()=>{$('activity-list').hidden=!$('activity-list').hidden;});
$('new-chat').addEventListener('click',async()=>{if(busy){toast('Arrêtez la tâche en cours avant de commencer une nouvelle conversation.');return;}try{await api('history/clear',{method:'POST'});$('conversation').replaceChildren();$('conversation').classList.remove('visible');$('welcome').hidden=false;$('activity').hidden=true;}catch(e){toast(e.message);}});
function openSettings(){$('settings-dialog').showModal();}
$('settings-button').addEventListener('click',openSettings);$('profile-button').addEventListener('click',openSettings);
async function save(values){try{await api('settings',{method:'POST',body:JSON.stringify(values)});refresh();}catch(e){toast(e.message);}}
$('profile-select').addEventListener('change',e=>save({profile:e.target.value}));$('speak-toggle').addEventListener('change',e=>save({speak:e.target.checked}));$('desktop-toggle').addEventListener('change',e=>save({desktop:e.target.checked}));
$('grant-permissions').addEventListener('click',async()=>{try{await api('permissions',{method:'POST'});toast('Activez les deux autorisations de CuaDriver dans Réglages Système.');}catch(e){toast(e.message);}});
$('check-permissions').addEventListener('click',async()=>{try{const result=await(await api('permissions/check',{method:'POST'})).json();toast(result.ready?'Jarvis peut maintenant utiliser vos applications.':'Les autorisations de CuaDriver ne sont pas encore actives.');refresh();}catch(e){toast(e.message);}});
function toggleRecording(){if(busy)return;if(window.webkit?.messageHandlers?.jarvis){window.webkit.messageHandlers.jarvis.postMessage({action:'record'});}else{toast('La dictée est disponible dans l’application Jarvis pour Mac.');}}
$('mic').addEventListener('click',toggleRecording);
window.jarvisNative={
  recording(value){recording=value;$('mic').classList.toggle('recording',value);$('recording-label').hidden=!value;$('orb').classList.toggle('active',value||busy);},
  error(text){this.recording(false);toast(text);},
  async audio(base64){this.recording(false);$('recording-label').textContent='Transcription sur votre Mac…';$('recording-label').hidden=false;try{const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));const result=await(await api('transcribe',{method:'POST',body:new Blob([bytes],{type:'audio/wav'})})).json();if(result.text)await send(result.text);else toast('Aucune parole reconnue. Essayez de nouveau.');}catch(e){toast(e.message);}finally{window.webkit?.messageHandlers?.jarvis.postMessage({action:'voice-finished'});$('recording-label').hidden=true;$('recording-label').textContent='Je vous écoute… Cliquez à nouveau pour envoyer.';}},
  settings:openSettings,toggleRecording
};
document.addEventListener('keydown',e=>{if(e.metaKey&&e.key===','){e.preventDefault();openSettings();}if(e.key==='Escape'&&busy)$('stop').click();});
async function syncSources(){
  if(busy)return;
  try{
    const data=await(await api('activity')).json();if(data.status!=='completed')return;
    const users=document.querySelectorAll('.message.user .message-body');if(users.length&&users[users.length-1].textContent!==data.request)return;
    const assistants=document.querySelectorAll('.message.assistant');const block=assistants[assistants.length-1];if(!block||block.querySelector('.source-list'))return;
    const sources=new Map();for(const event of data.events||[]){const result=event.result||{};
      for(const source of [...(result.results||[]),...(result.source?[result.source]:[])])if(/^https?:\/\//.test(source.url||''))sources.set(source.url,source.title||source.url);
    }
    if(!sources.size)return;
    const details=document.createElement('details');details.className='source-list';const summary=document.createElement('summary');summary.textContent='Sources';details.append(summary);
    for(const[url,title]of sources){const row=document.createElement('div'),link=document.createElement('a');link.href=url;link.textContent=title;link.rel='noreferrer';row.append(link);details.append(row);}block.append(details);
  }catch{}
}
let historySignature='';
async function syncHistory(){
  if(busy)return;
  try{const data=await(await api('history')).json();if(busy)return;const signature=JSON.stringify(data.messages);
    if(signature===historySignature)return;const oldScroll=$('conversation').scrollTop;historySignature=signature;$('conversation').replaceChildren();data.messages.forEach(m=>message(m.role,m.text,false));if(!followConversation)$('conversation').scrollTop=oldScroll;
  }catch{}
}
async function init(){await refresh();try{const data=await(await api('history')).json();data.messages.forEach(m=>message(m.role,m.text,false));historySignature=JSON.stringify(data.messages);}catch{}setInterval(refresh,12000);setInterval(syncHistory,1500);setInterval(syncSources,1500);}
init();
