"""Read-only browser checks against the running local app; no model calls."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':360,'height':600})
    page.add_init_script("window.__nativeCalls=[];window.webkit={messageHandlers:{jarvis:{postMessage:m=>window.__nativeCalls.push(m)}}};")
    page.route('**/api/activity',lambda r:r.fulfill(json={'id':None,'status':'idle','events':[],'speaking':False}))
    page.goto('http://127.0.0.1:8766/overlay')
    page.wait_for_function('Boolean(window.jarvisOverlay)')
    page.evaluate("jarvisOverlay.listening();jarvisOverlay.transcript('Une longue demande qui doit rester entièrement accessible. '.repeat(70)+'FIN');")
    page.wait_for_timeout(250)
    height=page.evaluate("__nativeCalls.filter(m=>m.action==='resize').at(-1).value.height")
    assert 400<height<500
    assert page.locator('#detail').inner_text()=='Texte complet · défilez pour lire'
    response=page.locator('#response')
    assert response.inner_text().endswith('FIN')
    assert response.evaluate('(e)=>e.scrollHeight>e.clientHeight')
    response.evaluate('(e)=>e.scrollTop=e.scrollHeight')
    assert response.evaluate('(e)=>Math.abs(e.scrollHeight-e.scrollTop-e.clientHeight)<3')
    page.evaluate("jarvisOverlay.listening();jarvisOverlay.transcript('Ouvre Pages.');")
    page.wait_for_timeout(250)
    short=page.evaluate("__nativeCalls.filter(m=>m.action==='resize').at(-1).value.height")
    assert short<160
    page.locator('#panel').hover()
    assert page.evaluate("__nativeCalls.some(m=>m.action==='hold'&&m.value===true)")
    page.emulate_media(reduced_motion='reduce')
    assert page.locator('.voice-mark i').first.evaluate('(e)=>getComputedStyle(e).animationName')=='none'
    page.set_viewport_size({'width':360,'height':150})
    page.screenshot(path=str(ROOT/'Documents/jarvis-overlay-apercu.png'))
    main=browser.new_page(viewport={'width':1120,'height':790})
    errors=[]
    main.on('pageerror',lambda e:errors.append(str(e)))
    main.route('**/api/history',lambda r:r.fulfill(json={'messages':[]}))
    main.route('**/api/activity',lambda r:r.fulfill(json={'id':None,'status':'idle','events':[]}))
    main.goto('http://127.0.0.1:8766/#token='+(ROOT/'.state/token').read_text().strip())
    main.wait_for_timeout(400)
    main.screenshot(path=str(ROOT/'Documents/interface-jarvis-accueil.png'))
    main.evaluate("message('user','Longue demande. '.repeat(150));message('assistant','Réponse complète.\\n'.repeat(100)+'FIN DE LA RÉPONSE');")
    main.wait_for_timeout(250)
    assert main.locator('#conversation').evaluate('(e)=>e.scrollHeight>e.clientHeight')
    assert main.locator('.message.assistant').inner_text().endswith('FIN DE LA RÉPONSE')
    main.locator('#prompt').fill('Longue dictée à lire et à corriger.\n'*45)
    metrics=main.locator('#prompt').evaluate('(e)=>({height:e.clientHeight,scroll:e.scrollHeight})')
    assert metrics['height']<=240 and metrics['scroll']>metrics['height']
    for width in [1120,760,390]:
        main.set_viewport_size({'width':width,'height':790})
        assert main.evaluate('document.body.scrollWidth<=innerWidth')
    assert not errors
    result={'overlay_long_height':height,'overlay_short_height':short,'entire_text_scrollable':True,'hover_retains_panel':True,'reduced_motion':True,'composer':metrics,'viewports':[1120,760,390],'javascript_errors':errors}
    (ROOT/'Documents/validation-interface-navigateur.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    browser.close()
