import pipeline


def test_style_summary_leaves_out_the_reference_domain():
    summary = pipeline.style_summary({'domain': '细胞信号转导', 'style': 'flat vector',
                                      'palette': ['#ffffff']})
    assert '细胞信号转导' not in summary
    assert 'flat vector' in summary


def test_vision_instruction_keeps_names_out_of_style_fields():
    assert '只放进 labels' in pipeline.VISION_INSTRUCTION


def _fake_rewrite(monkeypatch, replies):
    seen = []
    def fake_chat(config, messages, **kwargs):
        seen.append(messages[1]['content'])
        return replies.pop(0)
    monkeypatch.setattr(pipeline, '_chat', fake_chat)
    monkeypatch.setattr(pipeline, 'chat_json', lambda *a, **k: {'equivalent': True})
    return seen


CFG = {'text': {'base_url': 'http://127.0.0.1:9', 'model': 'm'}}


def test_optimize_brief_tells_the_rewrite_not_to_borrow_reference_content(monkeypatch):
    seen = _fake_rewrite(monkeypatch, ['EGFR 激活 PI3K'])
    assert pipeline.optimize_brief('EGFR 激活 PI3K', CFG, style='磷酸化标记；flat vector')
    assert '原文没有的一律不得写入' in seen[0] and '磷酸化标记' in seen[0]


def test_retry_keeps_the_guard_and_adds_nothing_without_a_style(monkeypatch):
    seen = _fake_rewrite(monkeypatch, ['', 'EGFR 激活 PI3K', '', 'EGFR 激活 PI3K'])
    pipeline.optimize_brief('EGFR 激活 PI3K', CFG, style='flat vector')
    assert '原文没有的一律不得写入' in seen[1]
    pipeline.optimize_brief('EGFR 激活 PI3K', CFG)
    assert seen[3] == 'EGFR 激活 PI3K'


def test_audit_allows_layout_but_still_forbids_new_science(monkeypatch):
    rule = pipeline.BRIEF_AUDIT_INSTRUCTION
    assert '阅读顺序' in rule and '区域名标签' in rule and '原文已有的关系画成箭头' in rule
    assert '修饰（如磷酸化）' in rule and '删除或替换原文实体' in rule and '否定' in rule
    seen = []
    monkeypatch.setattr(pipeline, '_chat', lambda *a, **k: 'EGFR 激活 PI3K')
    monkeypatch.setattr(pipeline, 'chat_json', lambda cfg, msgs, **k: seen.append(msgs[0]['content']) or {'equivalent': True})
    pipeline.optimize_brief('EGFR 激活 PI3K', CFG)
    assert seen == [rule]
