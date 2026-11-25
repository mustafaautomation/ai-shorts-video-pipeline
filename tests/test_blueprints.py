import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_n8n_workflow_calls_the_pipeline_api() -> None:
    document = json.loads((ROOT / "blueprints" / "n8n-shorts-pipeline.json").read_text())
    names = {node["name"] for node in document["nodes"]}
    assert "Topic webhook" in names
    assert "Generate and render" in names
    blob = json.dumps(document)
    assert "/v1/pipeline" in blob
    assert "dry_run" in blob
    assert document["connections"]["Topic webhook"]["main"][0][0]["node"] == "Generate and render"


def test_make_blueprint_calls_the_pipeline_api() -> None:
    document = json.loads((ROOT / "blueprints" / "make-shorts-scenario.json").read_text())
    modules = [item["module"] for item in document["flow"]]
    assert "gateway:CustomWebHook" in modules
    assert "http:ActionSendData" in modules
    blob = json.dumps(document)
    assert "/v1/pipeline" in blob
    assert document["name"]
