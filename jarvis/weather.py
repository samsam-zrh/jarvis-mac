"""Current weather data for concise answers, from Open-Meteo's free API."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx


def weather_forecast(city: str, day: str = 'tomorrow') -> dict:
    """Prévision météo actuelle pour une ville explicite. day: today, tomorrow ou date ISO. Si aucune ville n’est connue, demander la ville avant d’appeler. Retourne conditions et températures ; réponse utilisateur en une phrase, sans liste de sources."""
    if not city.strip():
        raise ValueError('Pour quelle ville ?')
    with httpx.Client(timeout=12, trust_env=False) as client:
        found=client.get('https://geocoding-api.open-meteo.com/v1/search',params={'name':city,'count':5,'language':'fr'})
        found.raise_for_status()
        places=found.json().get('results',[])
        if not places:
            raise ValueError('Ville introuvable : '+city)
        place=max(places,key=lambda p:p.get('population',0))
        local_date=datetime.now(ZoneInfo(place.get('timezone','Europe/Paris'))).date()
        selected=(local_date + timedelta(days=1)).isoformat() if day=='tomorrow' else local_date.isoformat() if day=='today' else day
        response=client.get('https://api.open-meteo.com/v1/forecast',params={'latitude':place['latitude'],'longitude':place['longitude'],'daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max','timezone':place.get('timezone','auto'),'forecast_days':16})
        response.raise_for_status()
        daily=response.json()['daily']
        if selected not in daily['time']:
            raise ValueError('Date hors de la période de prévision disponible')
        index=daily['time'].index(selected)
        code=daily['weather_code'][index]
        condition=('ensoleillé' if code==0 else 'quelques nuages' if code in (1,2) else 'couvert' if code==3 else 'brouillard' if code in (45,48) else 'bruine' if 51<=code<=57 else 'pluie' if 61<=code<=67 else 'neige' if 71<=code<=77 else 'averses' if 80<=code<=82 else 'averses de neige' if code in (85,86) else 'orage' if code>=95 else 'conditions variables')
        return {'city':place['name'],'country':place.get('country'),'date':selected,'condition':condition,'min_c':daily['temperature_2m_min'][index],'max_c':daily['temperature_2m_max'][index],'rain_probability_percent':daily['precipitation_probability_max'][index],'source':{'title':'Open-Meteo, CC BY 4.0','url':'https://open-meteo.com/'},'retrieved_at':datetime.now().astimezone().isoformat()}
