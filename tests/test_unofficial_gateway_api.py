"""Unofficial gateway option: saving requires an explicit, server-stamped risk acknowledgement.

Rylume ships no gateway code. The user runs an OpenAI-compatible gateway
themselves and only its address is stored; these tests pin the consent gate.
"""
import json
import time

import app_server
from test_scene_api import studio  # noqa: F401  (pytest fixture)

GATEWAY = {"base_url": "http://127.0.0.1:1/v1", "model": "gateway-model", "provider": "unofficial"}


def stored():
    return json.loads(app_server.CONFIG_PATH.read_text(encoding="utf-8"))


def test_unofficial_gateway_without_ack_is_rejected_and_nothing_is_saved(studio):
    before = stored()
    code, value = studio("/api/config", {"text": dict(GATEWAY)})
    assert code == 400, value
    assert value.get("code") == "unofficial_ack_required"
    assert stored() == before, "A rejected save must not touch the stored config"


def test_wrong_ack_version_is_rejected(studio):
    code, value = studio("/api/config", {"text": dict(GATEWAY), "unofficial_ack": {"version": 999}})
    assert code == 400, value
    assert "provider" not in stored().get("text", {})


def test_ack_is_stamped_by_server_and_kept_for_later_saves(studio):
    start = int(time.time())
    code, value = studio("/api/config", {"text": dict(GATEWAY), "unofficial_ack": {"version": 1, "at": 1}})
    assert code == 200, value
    ack = stored()["unofficial_ack"]
    assert ack["version"] == 1 and ack["at"] >= start, "The client timestamp must never be trusted"
    assert value["config"]["text"]["provider"] == "unofficial"
    assert value["config"]["unofficial_ack"]["version"] == 1

    # A later partial save (e.g. only quality) keeps both the gateway and the ack.
    code, value = studio("/api/config", {"quality": "standard"})
    assert code == 200, value
    assert stored()["text"]["provider"] == "unofficial"
    assert stored()["unofficial_ack"] == ack

    # A second gateway section is allowed without asking again.
    code, value = studio("/api/config", {"image": {**GATEWAY, "model": "gateway-image"}})
    assert code == 200, value
    assert stored()["image"]["provider"] == "unofficial"


def test_switching_back_to_custom_drops_provider_but_keeps_ack(studio):
    code, value = studio("/api/config", {"text": dict(GATEWAY), "unofficial_ack": {"version": 1}})
    assert code == 200, value
    code, value = studio("/api/config", {"text": {"base_url": "http://127.0.0.1:2/v1", "model": "m", "provider": "custom"}})
    assert code == 200, value
    assert "provider" not in stored()["text"]
    assert "provider" not in value["config"]["text"]
    assert stored()["unofficial_ack"]["version"] == 1
    assert not app_server.uses_unofficial_gateway(stored())


def test_old_configs_without_provider_load_unchanged():
    old = {"text": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen", "api_key": ""},
           "image": {"base_url": "http://127.0.0.1:7860/v1", "model": "flux"}}
    config = app_server.normalize_config(json.loads(json.dumps(old)))
    for key in ("text", "image", "vision"):
        assert "provider" not in config[key]
    assert "unofficial_ack" not in config
    assert config["text"]["base_url"] == old["text"]["base_url"]
    assert not app_server.uses_unofficial_gateway(config)


def test_unknown_provider_values_are_treated_as_custom():
    config = app_server.normalize_config({"text": {"base_url": "http://x/v1", "model": "m", "provider": "ark"},
                                          "unofficial_ack": "yes"})
    assert "provider" not in config["text"]
    assert "unofficial_ack" not in config, "A malformed ack must not count as consent"


def test_hand_edited_config_with_gateway_but_no_ack_still_blocks_next_save(studio):
    # Someone edits config.json by hand: the gate applies on the next UI save.
    raw = stored()
    raw["text"] = dict(GATEWAY)
    app_server.CONFIG_PATH.write_text(json.dumps(raw), encoding="utf-8")
    code, value = studio("/api/config", {"quality": "hd"})
    assert code == 400, value
