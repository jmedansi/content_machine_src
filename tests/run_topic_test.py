import sys
from pathlib import Path

# Ensure repo root is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared_agents.topic_finder.agent import suggest_persona_topics
import json

def run():
    # Test: account_id=1, persona 'post_court'
    res = suggest_persona_topics('post_court', count=3, account_id=1, platform='facebook')
    try:
        print('SUCCESS:', res.success)
        if res.success:
            print(json.dumps(res.data, ensure_ascii=False, indent=2))
        else:
            print('ERROR_CAUSE:', res.error_cause)
            print(json.dumps(res.data or {}, ensure_ascii=False, indent=2))
    except Exception as e:
        print('Exception printing result:', e)

if __name__ == '__main__':
    run()
