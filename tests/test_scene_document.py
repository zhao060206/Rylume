"""User-visible invariants for scene editing and reproducible examples."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from scene_document import (
    RevisionConflict, SceneError, SceneRepository, apply_operations, audit_scene,
    empty_scene, normalize_scene,
)
from scene_examples import EXAMPLES, make_example


def small_scene():
    scene = empty_scene()
    scene["objects"] = [
        {"id":"a","type":"kinase","label":"A","x":20,"y":20,"w":14,"h":10},
        {"id":"b","type":"protein","label":"B","x":60,"y":20,"w":14,"h":10},
    ]
    scene["relations"] = [{"id":"ab","source":"a","target":"b","type":"inhibits"}]
    scene["requirements"] = {"objects":["a","b"],"relations":["ab"]}
    return normalize_scene(scene)


def test_one_gesture_changes_only_selected_object_and_keeps_identity():
    scene = small_scene()
    before = copy.deepcopy(scene)
    after = apply_operations(scene,[{"op":"update","id":"a","changes":{"x":31,"label":"p-A"}}])
    assert scene == before
    assert after["objects"][1] == before["objects"][1]
    assert after["relations"] == before["relations"]
    assert after["objects"][0]["id"] == "a"
    assert after["objects"][0]["x"] == 31


def test_invalid_batch_cannot_partially_modify_original():
    scene = small_scene()
    with pytest.raises(SceneError):
        apply_operations(scene,[{"op":"update","id":"a","changes":{"x":31}},
                                 {"op":"update","id":"b","changes":{"font_size_pt":3}}])
    assert scene["objects"][0]["x"] == 20


def test_selected_ai_patch_cannot_change_neighbor_or_canvas():
    scene = small_scene()
    for ops in ([{"op":"update","id":"b","changes":{"x":10}}],
                [{"op":"canvas","width_mm":90}]):
        with pytest.raises(SceneError):
            apply_operations(scene,ops,allowed_ids={"a","ab"})


def test_remove_is_reversible_and_missing_requirement_is_visible():
    scene = small_scene()
    removed = apply_operations(scene,[{"op":"remove","id":"a"}])
    assert not removed["relations"]
    assert {f["code"] for f in audit_scene(removed)["findings"]} >= {"required-object","required-relation"}
    restored = apply_operations(removed,[{"op":"replace","scene":scene}])
    assert restored == scene


def test_revision_cas_only_one_concurrent_edit_wins_and_old_export_is_unchanged(tmp_path):
    repo = SceneRepository(tmp_path)
    first = repo.commit(small_scene())
    old_svg = (tmp_path/"revisions"/"1"/"result.svg").read_bytes()

    def update(x):
        try:
            return repo.patch(1,[{"op":"update","id":"a","changes":{"x":x}}])["revision"]
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update,[32,44]))
    assert sorted(map(str,results)) == ["2","conflict"]
    assert repo.read(1) == first["scene"]
    assert (tmp_path/"revisions"/"1"/"result.svg").read_bytes() == old_svg
    assert repo.read()["revision"] == 2
    # A new repository instance can recover the same HEAD after restart.
    assert SceneRepository(tmp_path).read() == repo.read()


@pytest.mark.parametrize("example",[e["id"] for e in EXAMPLES])
def test_examples_preserve_all_scientific_requirements_and_physically_readable_text(example):
    scene = make_example(example)
    assert scene["source_text"]
    assert scene["requirements"]["objects"] == [o["id"] for o in scene["objects"]]
    assert scene["requirements"]["relations"] == [r["id"] for r in scene["relations"]]
    assert all(o["evidence"] in scene["source_text"] for o in scene["objects"])
    assert all(o["font_size_pt"] >= 7 for o in scene["objects"])
    assert not [f for f in audit_scene(scene)["findings"] if f["severity"] == "error"]
    assert not any(word in json.dumps(scene).lower() for word in ("embodied ai","physical priors","latent inference"))


def test_three_pathways_and_four_vesicle_states_are_distinct():
    scenes = [make_example(k) for k in ("egfr","jak_stat","tgf_smad")]
    signatures = {tuple((o["type"],o["label"],o["state"],o["compartment"]) for o in s["objects"]) for s in scenes}
    assert len(signatures) == 3
    example = make_example("exosome")
    assert len({(o["type"],o["state"]) for o in example["objects"]}) == 4


def test_narrow_layout_reflows_without_shrinking_fonts_or_dropping_objects():
    scene = make_example("jak_stat")
    narrow = apply_operations(scene,[{"op":"canvas","width_mm":90,"height_mm":150,"reflow":True}])
    assert {o["id"] for o in narrow["objects"]} == {o["id"] for o in scene["objects"]}
    assert [o["font_size_pt"] for o in narrow["objects"]] == [o["font_size_pt"] for o in scene["objects"]]
    assert not [f for f in audit_scene(narrow)["findings"] if f["severity"]=="error"]


def test_markup_and_nonfinite_geometry_never_reach_renderer():
    scene = small_scene()
    for change in ({"x":float("nan")},{"fill":"red\" onload=\"alert(1)"},{"type":"script"}):
        with pytest.raises(SceneError):
            apply_operations(scene,[{"op":"update","id":"a","changes":change}])


def test_planner_reports_unsupported_evidence_instead_of_claiming_verification(monkeypatch):
    import scene_planner
    spec = {"title":"Signal","layout":"network","compartments":[],
            "objects":[{"id":"a","type":"protein","label":"A","evidence":"A"},
                       {"id":"b","type":"protein","label":"B","evidence":"B"}],
            "relations":[{"id":"ab","source":"a","target":"b","type":"activates","evidence":"invented link"}],
            "unresolved":[]}
    monkeypatch.setattr(scene_planner,"_request",lambda *a,**k:(spec,0.1))
    scene,_ = scene_planner.plan_scene("A and B",{"text":{"model":"fake","base_url":"unused"}})
    assert scene["relations"][0]["uncertain"]
    assert scene["unresolved"]
    assert audit_scene(scene)["status"] == "needs_attention"


def test_planner_retries_bad_structure_once_and_never_falls_back_to_wrong_template(monkeypatch):
    import scene_planner
    calls = []
    def request(*args,**kwargs):
        calls.append(1)
        return {"objects":[],"relations":[],"unresolved":[]},0
    monkeypatch.setattr(scene_planner,"_request",request)
    with pytest.raises(SceneError):
        scene_planner.plan_scene("A",{"text":{"model":"fake","base_url":"unused"}})
    assert len(calls)==2


def test_cancelled_planning_never_calls_provider(monkeypatch):
    import scene_planner
    monkeypatch.setattr(scene_planner,"_request",lambda *a,**k:pytest.fail("provider must not be called"))
    with pytest.raises(InterruptedError):
        scene_planner.plan_scene("A",{},cancelled=lambda:True)
