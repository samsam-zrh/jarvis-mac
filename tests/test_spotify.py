import pytest
from jarvis import spotify


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setattr(spotify, "STATE", tmp_path)


def arrange(monkeypatch, tree):
    monkeypatch.setattr(spotify,'open_item',lambda **kwargs:None)
    monkeypatch.setattr(spotify,'_remember',lambda name:None)
    def call(name, arguments):
        if name=='start_session':return {'active':True}
        if name=='launch_app':return {'pid':1}
        if name=='list_windows':return {'windows':[{'window_id':2,'title':'Spotify','bounds':{'width':900,'height':800}}]}
        if name=='get_window_state':return {'snapshot_id':'s1','tree_markdown':tree}
        raise AssertionError('An ambiguous/unrelated playlist must not be clicked')
    monkeypatch.setattr(spotify,'_call',call)


def test_playlist_prefix_is_not_a_verified_match(monkeypatch):
    arrange(monkeypatch,'- [1] AXButton (Mettre en pause : GDM ancien) [actions=[press]]\n- [2] AXButton "GDM ancien Playlist • User" [actions=[press]]')
    with pytest.raises(ValueError,match='Playlist non trouvée'):
        spotify.play_spotify('GDM')


def test_decorative_emoji_does_not_change_playlist_identity(monkeypatch):
    arrange(monkeypatch,'- [1] AXButton (Mettre en pause : GDM 🫳🔵 🫴🔴 🫸🟣) [actions=[press]]')
    assert spotify.play_spotify('GDM')['verified'] is True


def test_ampersand_and_spoken_and_are_same_playlist():
    assert spotify._library_matches('You and me ❤️ Playlist • Emma', 'You & Me')
    assert spotify._control_matches('Mettre en pause : You and me ❤️', 'You & Me', ('mettre en pause',))


def test_select_library_then_play_with_spoken_name(monkeypatch):
    arrange(monkeypatch, '')
    original = spotify._call
    clicks = []
    def call(name, arguments):
        if name == 'click':
            clicks.append(arguments['element_token'])
            return {}
        if name == 'get_window_state':
            if not clicks:
                tree = '- [1] AXButton "You and me ❤️ Playlist • Emma" [actions=[press]]'
            elif len(clicks) == 1:
                tree = '- [2] AXButton (Lire : You and me ❤️) [actions=[press]]'
            else:
                tree = '- [3] AXButton (Mettre en pause : You and me ❤️) [actions=[press]]'
            return {'snapshot_id':'fresh'+str(len(clicks)), 'tree_markdown':tree}
        return original(name, arguments)
    monkeypatch.setattr(spotify, '_call', call)
    assert spotify.play_spotify('You & Me')['verified']
    assert clicks == ['fresh0:1', 'fresh1:2']


def test_search_selects_title_and_artist_without_remix_or_other_artist():
    tree = '''- [1] AXRow "First"
      - [2] AXButton (Lire : Chanson - Remix)
      - [3] AXLink (Artiste)
    - [4] AXRow "Second"
      - [5] AXButton (Lire : Chanson)
      - [6] AXLink (Autre artiste)
    - [7] AXRow "Third"
      - [8] AXButton (Lire : Chanson)
      - [9] AXLink (Artiste)
    '''
    result = spotify._search_candidates({'snapshot_id':'s1','tree_markdown':tree},'Chanson','Artiste')
    assert [r['element_token'] for r in result] == ['s1:8']


def test_search_requires_title_before_play(monkeypatch):
    monkeypatch.setattr(spotify,'_call',lambda *args:pytest.fail('Must validate before controlling UI'))
    with pytest.raises(ValueError):spotify.search_spotify('any music',play=True)
