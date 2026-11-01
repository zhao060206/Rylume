from model_review import vision_config


def test_empty_or_partial_vision_config_reuses_text_model():
    text = {'base_url': 'http://text.local/v1', 'model': 'text-model', 'api_key': 'secret'}
    assert vision_config({'text': text, 'vision': {}}) == text
    assert vision_config({'text': text, 'vision': {'base_url': 'http://vision.local/v1'}}) == text
    configured = {'base_url': 'http://vision.local/v1', 'model': 'vision-model'}
    assert vision_config({'text': text, 'vision': configured}) == configured
