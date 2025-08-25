from agentic.agent_loop import _validate_plan

def test_plan_whitelist_and_dedup():
    plan = {"steps":[
        {"tool":"screen","args":{"symbols":["AAPL"],"days":365}},
        {"tool":"delete_db","args":{}},  # should be dropped
        {"tool":"screen","args":{"symbols":["AAPL"],"days":365}},  # duplicate
    ]}
    clean = _validate_plan(plan)
    assert len(clean["steps"]) == 1 and clean["steps"][0]["tool"] == "screen"