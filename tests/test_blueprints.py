import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


N8N_PIPELINE = ROOT / "blueprints" / "n8n-shorts-pipeline.json"
STICKY = "n8n-nodes-base.stickyNote"
HTTP = "n8n-nodes-base.httpRequest"
STOP = "n8n-nodes-base.stopAndError"
TRIGGER = "09:00 daily"
PAID_NODES = ("fal.ai Flux", "fal.ai Kling / Veo", "ElevenLabs TTS", "Creatomate render")

# wait, poll, counter, done-IF, tries-left IF, failure node, config key that holds the cap
POLL_LOOPS = (
    (
        "Wait 10s — still",
        "Poll still status",
        "Count still poll",
        "Still COMPLETED?",
        "Still tries left?",
        "Still timed out",
        "maxStillPolls",
    ),
    (
        "Wait 30s",
        "Poll fal status",
        "Count clip poll",
        "COMPLETED?",
        "Clip tries left?",
        "Clip timed out",
        "maxClipPolls",
    ),
    (
        "Wait 15s — render",
        "Poll render",
        "Count render poll",
        "Render ready?",
        "Render tries left?",
        "Render timed out",
        "maxRenderPolls",
    ),
    (
        "Wait 10s — container",
        "Poll container status",
        "Count container poll",
        "status_code = FINISHED?",
        "Container tries left?",
        "Container timed out",
        "maxContainerPolls",
    ),
)


def _pipeline() -> dict:
    return json.loads(N8N_PIPELINE.read_text())


def _by_name(document: dict) -> dict[str, dict]:
    return {node["name"]: node for node in document["nodes"]}


def _outputs(document: dict, name: str) -> list[list[str]]:
    """Target node names per output index of one node."""
    main = document["connections"].get(name, {}).get("main", [])
    return [[target["node"] for target in output] for output in main]


def _targets(document: dict, name: str) -> set[str]:
    return {target for output in _outputs(document, name) for target in output}


def _reachable(document: dict, start: str, *, without: frozenset[str] = frozenset()) -> set[str]:
    seen: set[str] = set()
    queue = [start]
    while queue:
        name = queue.pop()
        if name in seen or name in without:
            continue
        seen.add(name)
        queue.extend(_targets(document, name))
    return seen


def _config(document: dict) -> dict[str, str]:
    assignments = _by_name(document)["Run config"]["parameters"]["assignments"]["assignments"]
    return {entry["name"]: entry["value"] for entry in assignments}


def test_n8n_workflow_matches_the_daily_canvas() -> None:
    document = _pipeline()
    names = {node["name"] for node in document["nodes"]}
    for expected in (
        "09:00 daily",
        "Run config",
        "Apify — scrape Reels",
        "Dedupe check",
        "New Reel?",
        "Transcribe (Whisper)",
        "Script + scene prompts",
        "Cost cap check",
        "Scene loop",
        "fal.ai Flux",
        "fal.ai Kling / Veo",
        "Poll fal status",
        "COMPLETED?",
        "Aggregate clips",
        "Clips + voice",
        "Render ready?",
        "Send video + buttons",
        "Which button?",
        "Log abandoned reel",
        "Dry run?",
        "Mock publish (dry run)",
        "IG container (REELS)",
        "status_code = FINISHED?",
        "media_publish",
        "TikTok init",
        "YouTube Shorts",
        "Write dedupe log",
        "Log the post",
    ):
        assert expected in names
    blob = json.dumps(document)
    assert "apify~instagram-reel-scraper" in blob
    assert "media_type" in blob or "REELS" in blob
    assert "dry_run" in blob
    assert _outputs(document, TRIGGER) == [["Run config"]]
    assert _outputs(document, "Run config") == [["Apify — scrape Reels"]]
    assert _outputs(document, "Which button?")[0] == ["Dry run?"]
    assert document["settings"]["errorWorkflow"]


def test_n8n_export_is_structurally_valid() -> None:
    document = _pipeline()
    nodes = document["nodes"]
    names = [node["name"] for node in nodes]
    ids = [node["id"] for node in nodes]
    assert len(names) == len(set(names))
    assert len(ids) == len(set(ids))
    for node in nodes:
        assert node["type"].startswith("n8n-nodes-base.")
        assert isinstance(node["typeVersion"], int | float)
        assert isinstance(node["parameters"], dict)
        x, y = node["position"]
        assert isinstance(x, int) and isinstance(y, int)

    # No dangling connections, on either end.
    known = set(names)
    for source, outputs in document["connections"].items():
        assert source in known, f"connection from unknown node {source!r}"
        for output in outputs["main"]:
            for target in output:
                assert target["node"] in known, f"{source!r} points at missing {target['node']!r}"
                assert target["type"] == "main"
                assert target["index"] >= 0

    # No orphans: every node that is not a sticky note runs downstream of the trigger.
    working = {node["name"] for node in nodes if node["type"] != STICKY}
    assert _reachable(document, TRIGGER) == working
    assert not any(
        node["name"] in document["connections"] for node in nodes if node["type"] == STICKY
    )

    # Readable canvas: no two working nodes share a slot, and each has room on its row.
    slots = [tuple(node["position"]) for node in nodes if node["type"] != STICKY]
    assert len(slots) == len(set(slots))
    rows: dict[int, list[int]] = {}
    for x, y in slots:
        rows.setdefault(y, []).append(x)
    for xs in rows.values():
        ordered = sorted(xs)
        assert all(right - left >= 200 for left, right in zip(ordered, ordered[1:], strict=False))


def test_n8n_poll_loops_are_capped_with_a_failure_branch() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    config = _config(document)
    for wait, poll, count, done, tries_left, failure, cap_key in POLL_LOOPS:
        assert nodes[wait]["type"] == "n8n-nodes-base.wait"
        assert nodes[poll]["type"] == HTTP
        assert nodes[poll]["parameters"]["method"] == "GET"
        assert nodes[done]["type"] == "n8n-nodes-base.if"
        assert nodes[tries_left]["type"] == "n8n-nodes-base.if"
        assert nodes[failure]["type"] == STOP
        assert nodes[failure]["parameters"]["errorMessage"]

        # wait -> poll -> count -> IF, and "not done" asks the cap before waiting again.
        assert _outputs(document, wait) == [[poll]]
        assert _outputs(document, poll) == [[count]]
        assert _outputs(document, count) == [[done]]
        assert _outputs(document, done)[1] == [tries_left]
        assert _outputs(document, tries_left) == [[wait], [failure]]
        assert wait not in _outputs(document, done)[0]

        # The counter goes up once per poll, and the IF compares it with a configured cap.
        assert "attempt: (prev.attempt || 0) + 1" in nodes[count]["parameters"]["jsCode"]
        conditions = nodes[tries_left]["parameters"]["conditions"]["conditions"]
        cap = conditions[0]
        assert cap["leftValue"] == "={{ $json.attempt }}"
        assert cap["operator"] == {"type": "number", "operation": "lt"}
        assert f"$('Run config').first().json.{cap_key}" in cap["rightValue"]
        assert f"$env.{_env_name(cap_key)}" in config[cap_key]

        # The wait is entered once from the submit call; the only way back is the cap check.
        entries = {source for source in nodes if wait in _targets(document, source)}
        (submit,) = entries - {tries_left}
        assert tries_left in entries
        assert nodes[submit]["type"] == HTTP
        assert nodes[submit]["parameters"]["method"] == "POST"


def _env_name(config_key: str) -> str:
    return "".join(f"_{char}" if char.isupper() else char.upper() for char in config_key)


def test_n8n_still_is_polled_before_image_to_video() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    assert _outputs(document, "fal.ai Flux") == [["Wait 10s — still"]]
    assert _outputs(document, "Still COMPLETED?")[0] == ["Get still URL"]
    assert _outputs(document, "Get still URL") == [["fal.ai Kling / Veo"]]
    assert nodes["Get still URL"]["parameters"]["url"] == "={{ $json.response_url }}"
    assert "image_url: $json.images[0].url" in nodes["fal.ai Kling / Veo"]["parameters"]["jsonBody"]
    # Kling is unreachable from Flux unless the still reported COMPLETED.
    blocked = _reachable(document, "fal.ai Flux", without=frozenset({"Get still URL"}))
    assert "fal.ai Kling / Veo" not in blocked


def test_n8n_clips_are_aggregated_before_the_merge() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    loop = nodes["Scene loop"]
    assert loop["type"] == "n8n-nodes-base.splitInBatches"
    assert loop["parameters"]["batchSize"] == 1
    done_output, loop_output = _outputs(document, "Scene loop")
    assert loop_output == ["fal.ai Flux"]
    assert done_output == ["Aggregate clips"]
    assert _outputs(document, "Scene clip") == [["Scene loop"]]

    aggregate = nodes["Aggregate clips"]
    assert aggregate["type"] == "n8n-nodes-base.aggregate"
    assert aggregate["parameters"]["aggregate"] == "aggregateAllItemData"
    assert aggregate["parameters"]["destinationFieldName"] == "clips"

    main = document["connections"]["Aggregate clips"]["main"]
    assert main == [[{"node": "Clips + voice", "type": "main", "index": 0}]]
    merge_inputs = {
        (source, target["index"])
        for source, outputs in document["connections"].items()
        for output in outputs["main"]
        for target in output
        if target["node"] == "Clips + voice"
    }
    assert merge_inputs == {
        ("Aggregate clips", 0),
        ("ElevenLabs TTS", 1),
        ("Voice needed?", 1),
    }
    assert "$json.clips.map" in nodes["Creatomate render"]["parameters"]["jsonBody"]


def test_n8n_approval_has_three_choices_and_a_regeneration_cap() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    rows = nodes["Send video + buttons"]["parameters"]["inlineKeyboard"]["rows"]
    # First row: the three ways forward. Second row: the way out.
    assert [[button["text"] for button in row["row"]["buttons"]] for row in rows] == [
        ["Approve", "Rewrite script", "Redo clips"],
        ["Reject"],
    ]
    buttons = [button for row in rows for button in row["row"]["buttons"]]
    all_choices = [button["additionalFields"]["url"].split("?choice=")[1] for button in buttons]
    assert all_choices == ["approve", "rewrite_script", "redo_clips", "reject"]
    choices = all_choices[:3]
    assert all("$execution.resumeUrl" in button["additionalFields"]["url"] for button in buttons)

    # The run pauses for the tap, with a time limit, and the Switch reads the tap.
    tap = nodes["Wait for tap"]["parameters"]
    assert tap["resume"] == "webhook"
    assert tap["limitWaitTime"] is True
    assert _outputs(document, "Send video + buttons") == [["Wait for tap"]]
    assert _outputs(document, "Wait for tap") == [["Regeneration budget"]]
    assert _outputs(document, "Regeneration budget") == [["Which button?"]]

    switch = nodes["Which button?"]
    rules = switch["parameters"]["rules"]["values"]
    assert [rule["outputKey"] for rule in rules] == [
        "Approve",
        "Rewrite script",
        "Redo clips",
        "Regeneration cap",
        "Reject",
    ]
    assert [rule["conditions"]["conditions"][0]["rightValue"] for rule in rules[:3]] == choices
    assert switch["parameters"]["options"]["fallbackOutput"] == "extra"
    assert _outputs(document, "Which button?") == [
        ["Dry run?"],
        ["Script + scene prompts"],
        ["Cost cap check"],
        ["Log abandoned reel"],
        ["Log abandoned reel"],
        ["No answer — end"],
    ]

    # Rewrite script redoes the words; Redo clips keeps them. Neither reruns the scrape.
    scrape = "Apify — scrape Reels"
    assert scrape not in _reachable(document, "Script + scene prompts")
    assert "Script + scene prompts" not in _reachable(
        document, "Cost cap check", without=frozenset({"Which button?"})
    )

    # The cap: counted per run, read from config, and it ends the run without a publish.
    budget = nodes["Regeneration budget"]["parameters"]["jsCode"]
    assert "regenerationsUsed >= cfg.maxRegenerations" in budget
    assert "'cap_reached'" in budget
    assert "$env.MAX_REGENERATIONS" in _config(document)["maxRegenerations"]
    assert _outputs(document, "Log abandoned reel") == [["Reel abandoned"]]
    assert _targets(document, "Reel abandoned") == set()
    assert _targets(document, "No answer — end") == set()


def test_n8n_cost_cap_gates_every_paid_call() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    assert "$env.COST_CAP_USD" in _config(document)["costCapUsd"]
    check = nodes["Cost cap check"]["parameters"]["jsCode"]
    assert "cfg.costCapUsd" in check
    assert "$runIndex" in check  # each regeneration pass is charged again
    assert _outputs(document, "Cost cap check") == [["Under cost cap?"]]
    under_cap, over_cap = _outputs(document, "Under cost cap?")
    assert over_cap == ["Cost cap reached"]
    assert nodes["Cost cap reached"]["type"] == STOP
    assert "COST_CAP_USD" in nodes["Cost cap reached"]["parameters"]["errorMessage"]
    assert set(under_cap) == {"Scenes", "Voice needed?"}

    # Without the IF's true branch, no paid node can be reached, on any pass.
    gate = frozenset({"Under cost cap?"})
    open_paths = _reachable(document, TRIGGER, without=gate)
    for paid in PAID_NODES:
        assert nodes[paid]["type"] == HTTP
        assert paid not in open_paths
    # Both regeneration targets pass back through the check.
    for output in _outputs(document, "Which button?")[1:3]:
        assert "Cost cap check" in _reachable(document, output[0], without=gate)


def test_n8n_dedupe_log_is_written_once_at_the_end() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    writers = [
        node["name"]
        for node in document["nodes"]
        if node["type"] == "n8n-nodes-base.code"
        and "data.used.push" in node["parameters"]["jsCode"]
    ]
    assert writers == ["Write dedupe log"]
    assert ".push(" not in nodes["Dedupe check"]["parameters"]["jsCode"]
    assert _outputs(document, "YouTube Shorts") == [["Write dedupe log"]]
    assert _outputs(document, "Write dedupe log") == [["Log the post"]]
    # Only an approved run that published, for real or as a dry run, reaches the write.
    assert _outputs(document, "Mock publish (dry run)") == [["Write dedupe log"]]
    assert "Write dedupe log" not in _reachable(
        document, TRIGGER, without=frozenset({"media_publish", "Mock publish (dry run)"})
    )
    assert "Write dedupe log" not in _reachable(document, TRIGGER, without=frozenset({"Dry run?"}))


def test_n8n_social_nodes_sit_behind_the_dry_run_guard() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    # Same switch and same default as the Python adapters: dry run unless set to false.
    setting = _config(document)["publishDryRun"]
    assert "$env.PUBLISH_DRY_RUN ?? 'true'" in setting
    assert "['0', 'false', 'no']" in setting

    guard = nodes["Dry run?"]
    assert guard["type"] == "n8n-nodes-base.if"
    condition = guard["parameters"]["conditions"]["conditions"][0]
    assert condition["leftValue"] == "={{ $('Run config').first().json.publishDryRun }}"
    assert condition["operator"]["operation"] == "true"
    assert _outputs(document, "Dry run?") == [["Mock publish (dry run)"], ["IG container (REELS)"]]

    # The dry-run branch holds no HTTP node, so it cannot call anything.
    mock = nodes["Mock publish (dry run)"]
    assert mock["type"] == "n8n-nodes-base.code"
    assert "sent: false" in mock["parameters"]["jsCode"]
    dry_branch = _reachable(document, "Mock publish (dry run)")
    assert not [name for name in dry_branch if nodes[name]["type"] == HTTP]

    # Every social node is reachable only through the guard, and only on its "false" output.
    social = [
        "IG container (REELS)",
        "Poll container status",
        "media_publish",
        "TikTok init",
        "YouTube Shorts",
    ]
    open_paths = _reachable(document, TRIGGER, without=frozenset({"Dry run?"}))
    live_branch = _reachable(document, "IG container (REELS)")
    for name in social:
        assert name not in open_paths
        assert name in live_branch
    graph_nodes = [
        node["name"]
        for node in document["nodes"]
        if node["type"] == HTTP and "graph.facebook.com" in node["parameters"]["url"]
    ]
    assert set(graph_nodes) <= set(social)

    # The note and the closing message say the same thing.
    posted = nodes["Posted"]["parameters"]["text"]
    assert "publishDryRun ?" in posted
    assert "nothing was sent to Instagram, TikTok, or YouTube" in posted
    assert "PUBLISH_DRY_RUN" in nodes["Lane 6"]["parameters"]["content"]


def test_n8n_rejected_or_exhausted_reels_are_logged_as_abandoned() -> None:
    document = _pipeline()
    nodes = _by_name(document)
    # Reject and the regeneration cap both end in the abandoned log, and nowhere else.
    cap_output, reject_output = _outputs(document, "Which button?")[3:5]
    assert cap_output == reject_output == ["Log abandoned reel"]
    sources = {name for name in nodes if "Log abandoned reel" in _targets(document, name)}
    assert sources == {"Which button?"}
    downstream = _reachable(document, "Log abandoned reel")
    assert downstream == {"Log abandoned reel", "Reel abandoned"}

    log = nodes["Log abandoned reel"]["parameters"]["jsCode"]
    assert "data.abandoned.push({ reelId, reason," in log
    assert "'rejected'" in log and "'regeneration_cap'" in log
    assert "$('Dedupe check').first().json.reelId" in log
    assert "will not be picked again" in nodes["Reel abandoned"]["parameters"]["text"]

    # The next day's Dedupe check reads that log, so the reel is skipped.
    check = nodes["Dedupe check"]["parameters"]["jsCode"]
    assert "(data.abandoned || []).map(a => String(a.reelId))" in check
    assert "!seen.has(idOf(i))" in check

    # A reel that keeps failing or going unanswered is started a capped number of times.
    assert _outputs(document, "New Reel?")[0] == ["Count reel attempt"]
    assert _outputs(document, "Count reel attempt") == [["Download source MP4"]]
    counter = nodes["Count reel attempt"]["parameters"]["jsCode"]
    assert "data.attempts[reelId] = (data.attempts[reelId] || 0) + 1" in counter
    assert "(attempts[idOf(i)] || 0) < cfg.maxReelAttempts" in check
    assert "$env.MAX_REEL_ATTEMPTS" in _config(document)["maxReelAttempts"]
    # Nothing paid runs before the attempt is counted.
    before_count = _reachable(document, TRIGGER, without=frozenset({"Count reel attempt"}))
    assert not set(PAID_NODES) & before_count


def test_env_example_lists_every_variable_the_canvas_reads() -> None:
    listed = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M))
    read = set(re.findall(r"\$env\.([A-Z][A-Z0-9_]*)", N8N_PIPELINE.read_text()))
    assert read
    assert read <= listed, sorted(read - listed)


def test_n8n_http_nodes_retry_and_time_out() -> None:
    document = _pipeline()
    http_nodes = [node for node in document["nodes"] if node["type"] == HTTP]
    assert len(http_nodes) == 18
    for node in http_nodes:
        assert node["retryOnFail"] is True, node["name"]
        assert node["maxTries"] >= 3, node["name"]
        assert node["waitBetweenTries"] >= 1000, node["name"]
        assert node["parameters"]["options"]["timeout"] > 0, node["name"]


def test_n8n_graph_api_version_is_read_from_one_place() -> None:
    document = _pipeline()
    assert _config(document)["graphApiVersion"] == "={{ $env.GRAPH_API_VERSION || 'v21.0' }}"
    assert N8N_PIPELINE.read_text().count("v21.0") == 1
    readers = [
        node["name"]
        for node in document["nodes"]
        if "$env.GRAPH_API_VERSION" in json.dumps(node["parameters"])
    ]
    assert readers == ["Run config"]
    graph_urls = [
        node["parameters"]["url"]
        for node in document["nodes"]
        if node["type"] == HTTP and "graph.facebook.com" in node["parameters"]["url"]
    ]
    assert len(graph_urls) == 3
    prefix = "=https://graph.facebook.com/{{ $('Run config').first().json.graphApiVersion }}/"
    assert all(url.startswith(prefix) for url in graph_urls)


def test_n8n_export_holds_no_secrets_or_account_names() -> None:
    document = _pipeline()
    for node in document["nodes"]:
        for reference in node.get("credentials", {}).values():
            assert set(reference) == {"id", "name"}
        params = json.dumps(node["parameters"])
        for marker in ("Bearer ", "Authorization", "access_token=", "api_key=", "sk-", "xoxb-"):
            assert marker not in params, node["name"]
    scrape = _by_name(document)["Apify — scrape Reels"]["parameters"]["jsonBody"]
    assert "username: $json.sourceUsernames" in scrape
    assert "$env.SOURCE_INSTAGRAM_USERNAMES" in _config(document)["sourceUsernames"]


def test_error_workflow_alerts_on_failure() -> None:
    document = json.loads((ROOT / "blueprints" / "n8n-error-workflow.json").read_text())
    names = {node["name"] for node in document["nodes"]}
    assert "On any failed node" in names
    assert "Alert — step failed" in names
    assert document["nodes"][0]["type"] == "n8n-nodes-base.errorTrigger"


def test_make_blueprint_covers_the_same_stages() -> None:
    document = json.loads((ROOT / "blueprints" / "make-shorts-scenario.json").read_text())
    blob = json.dumps(document)
    assert "apify~instagram-reel-scraper" in blob
    assert "queue.fal.run" in blob
    assert "media_type" in blob
    assert "dry_run" in blob
    assert document["name"]
