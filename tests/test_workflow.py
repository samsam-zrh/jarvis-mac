from jarvis.workflow import Workflow


def test_opening_gmail_cannot_prove_notes_was_opened():
    state=Workflow([{'goal':'Ouvrir Gmail','kind':'open_service','target':'gmail'},
        {'goal':'Ouvrir Notes','kind':'open_app','target':'Notes'}])
    state.observe('open_service',{'service':'gmail'},{'opened':True})
    assert state.state()['completed']==[1]
    assert state.state()['remaining']==['Ouvrir Notes']
    state.confirm_interface([1,2])
    assert state.state()['remaining']==['Ouvrir Notes']


def test_listing_tabs_cannot_prove_their_content_was_read():
    state=Workflow([{'goal':'Lire la page','kind':'read','target':''}])
    state.observe('browser_tabs',{}, {'tabs':[{'title':'Rendez-vous'}]})
    assert state.state()['completed']==[]
    state.observe('read_browser_tab',{'tab':2},{'text':'Le 3 novembre.'})
    assert state.state()['completed']==[1]


def test_preparing_a_draft_is_not_sending_it():
    state=Workflow([{'goal':'Envoyer le message','kind':'send_message','target':'Emma'}])
    state.observe('draft_message',{'recipient':'emma@example.com'},{'status':'draft','sent':False})
    state.confirm_interface([1])
    assert not state.state()['completed']
    state.observe('bureau_click',{}, {'success':True})
    state.confirm_interface([1])
    assert not state.state()['completed']
    state.observe('bureau_get_window_state',{}, {'text':'Message envoyé'})
    state.confirm_interface([1])
    assert state.state()['completed']==[1]


def test_verified_spotify_playback_covers_opening_and_playing():
    state=Workflow([{'goal':'Ouvrir Spotify','kind':'open_app','target':'Spotify'},
        {'goal':'Jouer la musique','kind':'play_music','target':'Song'}])
    state.observe('search_spotify',{'play':True},{'playing':True,'verified':True})
    assert state.state()['completed']==[1,2]


def test_named_contact_can_be_resolved_to_a_verified_address():
    state=Workflow([{'goal':'Préparer le message à Emma','kind':'draft_message','target':'Emma'}])
    state.observe('find_contacts',{'query':'Emma'},{'contacts':[{'name':'Emma Martin','emails':['contact@example.com'],'phones':[]}]})
    state.observe('draft_message',{'recipient':'contact@example.com','channel':'gmail'},
        {'status':'draft','sent':False,'recipient_resolved':True})
    assert state.state()['completed']==[1]
