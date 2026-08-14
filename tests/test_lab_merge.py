import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def test_template_contains_panel():
    tpl = (ROOT / 'dashboard' / 'templates' / 'views' / 'sections' / 'laboratoire.html').read_text(encoding='utf-8')
    assert 'validateAllPlannedTopics' in tpl, 'validateAllPlannedTopics button missing in template'
    assert 'planning-timeline' in tpl, 'planning-timeline container missing in template'

def test_js_contains_toggle():
    js = (ROOT / 'dashboard' / 'js' / 'planning.js').read_text(encoding='utf-8')
    assert 'function validateAllPlannedTopics' in js or 'validateAllPlannedTopics = (' in js, 'validateAllPlannedTopics function not found in JS'
    assert 'window.validateAllPlannedTopics' in js, 'window.validateAllPlannedTopics not exposed'

if __name__ == '__main__':
    try:
        test_template_contains_panel()
        test_js_contains_toggle()
        print('OK: lab merge sanity checks passed')
        sys.exit(0)
    except AssertionError as e:
        print('FAILED:', e)
        sys.exit(1)
