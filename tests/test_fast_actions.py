from datetime import datetime
import pytest
from jarvis.fast_actions import match_action, match_plan


def test_only_exact_app_requests_skip_model():
    assert match_action("Ouvre Safari s’il te plaît")["application"] == "Safari"
    assert match_action("Lance la calculatrice")["application"] == "Calculator"
    assert match_action("Ouvre mon document dans Pages") is None
    assert match_action("Ouvre Safari et efface mes téléchargements") is None


def test_simple_local_time_request():
    result = match_action("Quelle heure est-il ?")
    assert result["kind"] == "time"
    assert match_action("Quelle heure est-il à Tokyo ?") is None


def test_natural_spoken_app_formulation():
    assert match_action("ouvre-moi l’application Notes")["application"] == "Notes"


def test_transcriber_punctuation_keeps_multi_action_order():
    plan = match_plan("Ouvre Spotify. Lance la playlist GDM. Puis ouvre un Word.")
    assert [action["kind"] for action in plan] == ["open", "spotify", "document"]
    assert plan[1]["playlist"] == "gdm"


def test_partial_known_plan_does_not_discard_unknown_action():
    assert match_plan("Ouvre Spotify et efface mes téléchargements") is None


def test_conjunction_inside_playlist_is_not_an_action_separator():
    assert match_plan('lance la playlist toi et moi')[0]['playlist'] == 'toi et moi'


def test_open_document_by_name_has_a_direct_path():
    assert match_action('Ouvre le document Budget annuel')['kind']=='file'
    assert match_action('Ouvre le document Budget annuel')['query']=='budget annuel'


def test_direct_queries_preserve_names_and_accents():
    assert match_action('Cherche Édith Piaf sur YouTube')=={'kind':'service_search','service':'youtube','query':'Édith Piaf'}
    assert match_action('Joue Around the World sur Spotify')['play'] is True


def test_chained_controls_and_multiple_apps_skip_reasoning():
    assert [a['kind'] for a in match_plan('Coupe le son puis ouvre Notes et lance Safari')]==['audio','open','open']
    assert [a['application'] for a in match_plan('Ouvre Spotify, Notes et Safari')]==['Spotify','Notes','Safari']
    assert match_action('mets le volume à 40 %')['volume']==40


def test_keywords_inside_a_message_are_not_direct_actions():
    assert match_plan('Écris un message qui dit coupe le son puis ouvre Notes') is None
    assert match_action('Ne coupe pas le son') is None


def test_simple_send_request_can_skip_reasoning_without_losing_the_body():
    plan=match_plan('Tu peux envoyer un mail à Alex Test où tu lui dis bonjour ?')
    assert plan==[{'kind':'delivery','recipient':'Alex Test','body':'bonjour','channel':'gmail'}]
    plan=match_plan('Envoie un message à Alex Test : « Bonjour puis ouvre Notes »')
    assert len(plan)==1
    assert plan[0]['body']=='Bonjour puis ouvre Notes'


def test_multiple_actions_after_an_unquoted_send_request_keep_order():
    plan=match_plan('Envoie un message à Alex Test : bonjour puis ouvre Notes')
    assert [a['kind'] for a in plan]==['delivery','open']
