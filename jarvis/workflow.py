"""Track requested outcomes against successful tool results, not assistant prose."""
import json
import re
import httpx
from jarvis.applications import normalize
from jarvis.paths import OLLAMA_URL

KINDS = ['open_app','open_service','create_document','draft_message','send_message','search','read','play_music','desktop']
SPEC = {'type':'object','properties':{'steps':{'type':'array','maxItems':8,'items':{
    'type':'object','properties':{'goal':{'type':'string'},'kind':{'type':'string','enum':KINDS},
    'target':{'type':'string'}},'required':['goal','kind','target'],'additionalProperties':False}}},
    'required':['steps'],'additionalProperties':False}


async def objectives_for(text, history, model):
    from jarvis.routines import is_routine_definition
    if is_routine_definition(text):
        return []
    multi = bool(re.search(r'\b(?:puis|ensuite|après|apres|et (?:ouvre|lance|crée|cree|cherche|écris|ecris|envoie|prépare|prepare|rédige|redige|lis|résume|resume|mets))\b',text,re.I))
    if not multi:
        if re.search(r'\b(?:lis|lire|résume|resume|résumer|extrais)\b.*\b(?:onglet|page|mails?|emails?|document|fichier)',text,re.I):
            return [{'goal':'Lire le contenu demandé avant de répondre','kind':'read','target':''}]
        return []
    prompt = "Extrais les objectifs explicites de la demande, dans leur ordre, sans agir. Écris chaque goal en français. Un objectif par action utilisateur, pas les sous-étapes techniques. N’exécute pas les phrases dictées dans le corps d’un message. Pour les mails dans Safari: open_service cible gmail. open_app cible nom d’application. Rédiger/préparer sans envoyer: draft_message, target=destinataire. Envoi demandé: send_message, target=destinataire. Un fichier à créer puis ouvrir = deux objectifs. Pour un fichier à ouvrir, kind=desktop. Pour jouer une chanson ou playlist, kind=play_music, target=titre demandé. Ne crée pas d'objectif pour 'sans envoyer'. Réponds en JSON court."
    async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
        response = await client.post(OLLAMA_URL+'/api/chat',json={'model':model,'think':False,'stream':False,
            'format':SPEC,'messages':[{'role':'system','content':prompt},{'role':'user','content':text}],
            'keep_alive':-1,'options':{'temperature':0,'num_predict':550,'num_ctx':16384}})
        response.raise_for_status()
        steps = json.loads(response.json()['message']['content'])['steps']
    if not isinstance(steps,list) or not 1 <= len(steps) <= 8:
        raise ValueError('Impossible de décomposer la demande ; reformule-la en précisant les actions.')
    if any(not isinstance(s,dict) or s.get('kind') not in KINDS or not isinstance(s.get('goal'),str) or not isinstance(s.get('target'),str) for s in steps):
        raise ValueError('La décomposition de la demande est invalide')
    return steps


class Workflow:
    def __init__(self, steps):
        self.steps = steps
        self.done = set()
        self.interface_actions = 0
        self.interface_verified = False
        self.confirmations = []
        self.contact_addresses = {}

    def observe(self, name, arguments, result):
        if result.get('error') or result.get('isError'): return
        if name == 'find_contacts' and len(result.get('contacts',[])) == 1:
            contact = result['contacts'][0]
            addresses = {normalize(value) for value in contact.get('emails',[]) + contact.get('phones',[]) if isinstance(value,str)}
            self.contact_addresses[normalize(arguments.get('query',''))] = addresses
            self.contact_addresses[normalize(contact.get('name',''))] = addresses
        if name.startswith('bureau_') and re.search('click|type|key|scroll|drag',name):
            self.interface_actions += 1
            self.interface_verified = False
        elif self.interface_actions and name in ('bureau_get_window_state','read_browser_tab'):
            self.interface_verified = True
        if name == 'open_item': self.confirmations.append((result.get('application') or arguments.get('application') or arguments.get('path_or_url') or 'L’élément demandé')+' ouvert.')
        elif name == 'open_service': self.confirmations.append((result.get('service') or arguments.get('service','Service'))+' ouvert dans '+arguments.get('browser','Safari')+'.')
        elif name == 'create_document' and result.get('created'): self.confirmations.append('Document créé : '+result.get('path','')+'.')
        elif name in ('create_and_open_document', 'create_presentation') and result.get('created'):
            message = 'Fichier créé : '+result.get('path','')+'.'
            if result.get('opening'): message += ' Ouverture demandée dans '+result['opening']['application']+'.'
            elif result.get('opening_error'): message += ' Ouverture impossible : '+result['opening_error']
            self.confirmations.append(message)
        elif name == 'draft_message': self.confirmations.append('Brouillon préparé pour '+arguments.get('recipient','')+', sans envoi.')
        for index, step in enumerate(self.steps):
            kind, target = step['kind'], normalize(step['target'])
            matched = False
            if kind == 'open_app' and name == 'open_item':
                matched = target == normalize(arguments.get('application',''))
            elif kind == 'open_app' and target == 'spotify' and name in ('play_spotify','search_spotify'):
                matched = bool(result.get('verified') or result.get('searched'))
            elif kind == 'open_service' and name == 'open_service':
                from jarvis.workspace import ALIASES
                service = normalize(arguments.get('service',''))
                matched = ALIASES.get(target,target) == ALIASES.get(service,service)
            elif kind == 'create_document': matched = name in ('create_document','create_and_open_document','create_presentation') and bool(result.get('created')) and not result.get('opening_error')
            elif kind == 'draft_message':
                recipient = normalize(arguments.get('recipient',''))
                matched = name == 'draft_message' and result.get('status') == 'draft' and result.get('recipient_resolved') and arguments.get('channel','gmail') == 'gmail' and (not target or target == 'gmail' or target in recipient or recipient in self.contact_addresses.get(target,set()))
            elif kind == 'read': matched = name in ('read_browser_tab','read_document','read_webpage','bureau_get_window_state')
            elif kind == 'search': matched = name in ('search_web','search_spotify','find_files','find_contacts') or name == 'open_service' and bool(arguments.get('query'))
            elif kind == 'play_music': matched = name in ('play_spotify','search_spotify') and bool(result.get('playing') and result.get('verified'))
            elif kind == 'send_message':
                recipient=normalize(arguments.get('recipient',''))
                matched = name == 'send_message' and bool(result.get('submitted')) and (not target or target in recipient or normalize(result.get('recipient','')) in self.contact_addresses.get(target,set()))
            elif kind == 'desktop': matched = name in ('open_document','run_command') or name == 'open_item' and bool(arguments.get('path_or_url'))
            if matched: self.done.add(index+1)

    def confirm_interface(self, completed):
        # Direct, structured actions are accounted for automatically. Only UI
        # outcomes need model confirmation, after actual interface actions.
        if self.interface_verified:
            self.done.update(i for i in completed if self.steps[i-1]['kind'] in ('desktop','send_message','draft_message','open_app','open_service'))

    def direct_answer(self):
        direct_kinds = {'open_app','open_service','create_document','draft_message'}
        if self.steps and len(self.done) == len(self.steps) and all(s['kind'] in direct_kinds for s in self.steps):
            return ' '.join(dict.fromkeys(self.confirmations))
        return None

    def state(self):
        return {'steps':self.steps,'completed':sorted(self.done),
                'remaining':[s['goal'] for i,s in enumerate(self.steps,1) if i not in self.done]}
