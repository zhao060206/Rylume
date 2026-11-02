"""Real HTTP save: canonical deltas, conflicts and full-response compatibility."""
import json
from test_scene_api import studio, example


def apply_delta(scene, delta):
    scene = json.loads(json.dumps(scene))
    scene.update(delta['fields'])
    for field in ('objects', 'relations'):
        change = delta[field]
        items = {o['id']: o for o in scene[field]}
        for oid in change['removed']:
            del items[oid]
        for item in change['added']:
            items[item['id']] = item
        for item in change['updated']:
            target = items[item['id']]
            target.update(item['changes'])
            for key in item['unset']:
                del target[key]
        scene[field] = [items[oid] for oid in change.get('order', items)]
    return scene


def test_delta_save_matches_reopened_document_and_pins_revision(studio):
    job = example(studio)
    endpoint = f'/api/jobs/{job}/scene'
    _, first = studio(endpoint)
    original = first['scene']
    target = original['objects'][0]
    code, result = studio(endpoint, {'base_revision': 1, 'response': 'delta', 'operations': [
        {'op': 'update', 'id': target['id'], 'changes': {'label': 'Updated label', 'rotation': 450}},
        {'op': 'add', 'object': {'id': 'new_note', 'type': 'text', 'label': 'New note', 'x': 3, 'y': 4, 'w': 20, 'h': 4}},
        {'op': 'reorder', 'ids': ['new_note'] + [o['id'] for o in original['objects']]},
    ]}, 'PATCH')
    assert code == 200, result
    assert result['revision'] == 2 and 'scene' not in result and 'svg' not in result
    local = apply_delta(original, result['scene_delta'])
    _, reopened = studio(endpoint)
    assert local == reopened['scene']
    assert next(o for o in local['objects'] if o['id'] == target['id'])['rotation'] == 90
    assert f'data-revision="2"' in reopened['svg']
    code, _ = studio(endpoint, {'base_revision': 1, 'response': 'delta', 'operations': [
        {'op': 'update', 'id': target['id'], 'changes': {'label': 'Must not be written'}}]}, 'PATCH')
    assert code == 409
    _, unchanged = studio(endpoint)
    assert unchanged['scene'] == local
    code, removed = studio(endpoint, {'base_revision': 2, 'response': 'delta', 'operations': [
        {'op': 'remove', 'id': 'new_note'}]}, 'PATCH')
    assert code == 200
    _, reopened = studio(endpoint)
    assert apply_delta(local, removed['scene_delta']) == reopened['scene']
    # Existing clients still receive the established scene + SVG payload.
    code, compatible = studio(endpoint, {'base_revision': 3, 'operations': [
        {'op': 'update', 'id': target['id'], 'changes': {'label': target['label']}}]}, 'PATCH')
    assert code == 200 and compatible['scene']['revision'] == 4 and compatible['svg']


def test_audit_poll_preserves_review_and_author_state_without_artwork(studio):
    job = example(studio)
    endpoint = f'/api/jobs/{job}'
    _, full = studio(endpoint+'/scene')
    code, summary = studio(endpoint+'/audit')
    assert code == 200
    assert summary == {k: full[k] for k in ('ok', 'revision', 'audit')}
    code, _ = studio(endpoint+'/confirm', {'revision': full['revision']})
    assert code == 200
    _, summary = studio(endpoint+'/audit')
    assert summary['audit']['author_confirmed']
    _, full = studio(endpoint+'/scene')
    assert summary['audit'] == full['audit']


def test_template_and_glyph_changes_refresh_canonical_svg(studio):
    job = example(studio)
    endpoint=f'/api/jobs/{job}/scene'
    _, original=studio(endpoint)
    target=original['scene']['objects'][0]
    code, result=studio(endpoint,{'base_revision':1,'response':'delta','operations':[
        {'op':'update','id':target['id'],'changes':{'state':'activated'}}]},'PATCH')
    assert code==200
    assert 'scene_delta' not in result and result['svg'] and result['scene']['revision']==2
    code, resized=studio(endpoint,{'base_revision':2,'response':'delta','operations':[
        {'op':'canvas','width_mm':190,'height_mm':125,'reflow':False}]},'PATCH')
    assert code==200
    assert 'scene_delta' not in resized and 'width="190.0mm"' in resized['svg']
