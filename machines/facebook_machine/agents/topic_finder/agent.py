# Pass-through wrapper pointing to the shared topic_finder agent
from shared_agents.topic_finder.agent import (
    get_active_personas,
    get_recent_topics,
    format_recent_for_planner,
    generate_daily_plan,
    suggest_persona_topics
)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    
    res = generate_daily_plan(args.date, args.force)
    print(res)
    if res.success:
        print("Success!")
