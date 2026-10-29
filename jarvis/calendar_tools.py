"""Calendar.app automation using Apple's documented scripting interface."""
import json
from datetime import datetime

from jarvis.workspace import _jxa


def _dates(start, end):
    try:
        first, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
    except ValueError as error:
        raise ValueError('Dates ISO requises, par exemple 2026-10-30T09:00:00+01:00') from error
    if first.tzinfo is None or last.tzinfo is None or last <= first:
        raise ValueError('Dates avec fuseau horaire et fin après début requises')
    return first.isoformat(), last.isoformat()


def list_calendars() -> dict:
    """Lister les calendriers réellement connectés à Calendrier macOS et leurs identifiants (noms exacts ; les doublons sont ambigus). Une autorisation macOS peut être nécessaire."""
    return {'calendars': _jxa("JSON.stringify(Application('Calendar').calendars.name().map((name,i) => ({id:name,name:name,writable:Application('Calendar').calendars.at(i).writable()})));"), 'untrusted_content': True}


def calendar_events(start: str, end: str, calendar_id: str = '') -> dict:
    """Lire les rendez-vous entre deux dates ISO avec fuseau, maximum 31 jours et 100 résultats. calendar_id vide lit tous les calendriers connectés à Calendrier macOS. Les événements récurrents peuvent nécessiter une vérification dans l'interface."""
    start, end = _dates(start, end)
    if (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() > 31 * 86400:
        raise ValueError('Lecture limitée à 31 jours par appel')
    args = json.dumps({'start': start, 'end': end, 'id': calendar_id})
    script = '''const a=ARGS, app=Application('Calendar'), out=[];
const names=app.calendars.name();
for (let i=0;i<names.length;i++) {
 const c=app.calendars.at(i);
 if(a.id && names[i]!==a.id) continue;
 const events=c.events.whose({_and:[{startDate:{_lessThan:new Date(a.end)}},{endDate:{_greaterThan:new Date(a.start)}}]})();
 for(const e of events) {
  out.push({id:e.uid(),calendar:c.name(),title:e.summary(),start:e.startDate().toISOString(),end:e.endDate().toISOString(),location:e.location()});
  if(out.length>=101) break;
 }
 if(out.length>=101) break;
}
JSON.stringify(out.sort((a,b)=>a.start.localeCompare(b.start)));'''.replace('ARGS', args)
    events = _jxa(script, timeout=40)
    return {'events': events[:100], 'truncated': len(events) > 100, 'untrusted_content': True, 'recurrence_note': 'Vérifier les occurrences récurrentes dans Calendrier si nécessaire.'}


def create_calendar_event(calendar_id: str, title: str, start: str, end: str, location: str = '', notes: str = '') -> dict:
    """Ajouter un rendez-vous explicitement demandé dans un calendrier choisi via list_calendars. Dates ISO avec fuseau, titre et calendrier obligatoires. Sans invités ni envoi d'invitations. En cas d'heure ambiguë, demander une précision avant l'appel."""
    start, end = _dates(start, end)
    if not title.strip() or not calendar_id.strip():
        raise ValueError('Titre et calendrier requis')
    args = json.dumps(dict(id=calendar_id,title=title,start=start,end=end,location=location,notes=notes),ensure_ascii=False)
    script = '''const a=ARGS, app=Application('Calendar');
const names=app.calendars.name(), matches=names.map((name,i)=>name===a.id?i:-1).filter(i=>i>=0);
if(matches.length!==1) throw Error('Calendrier absent ou nom ambigu');
const c=app.calendars.at(matches[0]);
if(!c.writable()) throw Error('Calendrier non modifiable');
const e=app.Event({summary:a.title,startDate:new Date(a.start),endDate:new Date(a.end),location:a.location,description:a.notes});
c.events.push(e);
JSON.stringify({created:true,id:e.uid(),calendar:c.name(),title:e.summary(),start:e.startDate().toISOString(),end:e.endDate().toISOString()});'''.replace('ARGS', args)
    return _jxa(script)
