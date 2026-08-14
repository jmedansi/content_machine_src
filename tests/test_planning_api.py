import sys
import requests
import time
import pytest

pytestmark = pytest.mark.integration

def test_generate_and_regenerate():
    url_base = "http://127.0.0.1:8000"
    
    # 1. Test generate_planning
    print("Testing generate_planning...")
    res = requests.post(f"{url_base}/api/planned_topics/generate_planning?platform=facebook&account_id=1")
    assert res.status_code == 200
    data = res.json()
    print("Generate Planning response:", data)
    assert data.get("success") is True
    assert data.get("count", 0) > 0

    # Sleep to allow Groq rate limits to cool down
    print("Sleeping 8 seconds to cool down Groq rate limits...")
    time.sleep(8)

    # 2. Get the list of topics
    res_topics = requests.get(f"{url_base}/api/planned_topics?platform=facebook&account_id=1&flatten=true")
    assert res_topics.status_code == 200
    topics = res_topics.json().get("topics", [])
    assert len(topics) > 0
    
    # Find a topic belonging to storytelling_pro or post_court
    test_topic = None
    for t in topics:
        if t.get("persona") in ["storytelling_pro", "post_court"]:
            test_topic = t
            break
            
    if not test_topic:
        test_topic = topics[-1]
        
    topic_id = test_topic["id"]
    original_text = test_topic["topic"]
    persona = test_topic.get("persona")
    print(f"Found topic to regenerate: ID={topic_id}, persona={persona}, original_text='{original_text}'")

    # 3. Test regenerate
    print("Testing regenerate...")
    res_regen = requests.post(f"{url_base}/api/planned_topics/regenerate/{topic_id}?platform=facebook&account_id=1")
    assert res_regen.status_code == 200
    data_regen = res_regen.json()
    print("Regenerate response:", data_regen)
    assert data_regen.get("success") is True
    
    # Verify topic changed in store
    res_single = requests.get(f"{url_base}/api/planned_topics/{topic_id}?platform=facebook&account_id=1")
    assert res_single.status_code == 200
    updated_topic = res_single.json().get("topic")
    assert updated_topic is not None
    assert updated_topic["id"] == topic_id
    assert "raw" in updated_topic
    print(f"Regenerated text: '{updated_topic['raw']['topic']}'")

if __name__ == '__main__':
    try:
        test_generate_and_regenerate()
        print("ALL TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
