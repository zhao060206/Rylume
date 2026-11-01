"""Publication gates distinguish a source push from a usable app update."""
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from github_delivery import DeliveryError
from tools.verify_update_release import validate_release
import update_mirrors


@pytest.fixture
def release(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    monkeypatch.setattr(update_mirrors, 'PUBLIC_KEY', key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    name = 'Rylume-4.7.0-Windows-x64.zip'
    payload = b'reviewed-windows-installer'
    (tmp_path/name).write_bytes(payload)
    data = {'tag_name': 'v4.7.0', 'draft': False, 'prerelease': False, 'assets': [{
        'name': name, 'size': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest(),
        'browser_download_url': 'https://github.com/zhao060206/Rylume/releases/download/v4.7.0/'+name}]}
    def signed(value):
        raw = json.dumps(value).encode()
        return raw, base64.b64encode(key.sign(raw))
    return data, signed, tmp_path


def test_complete_update_matches_reviewed_local_installer(release):
    data, signed, folder = release
    asset = validate_release(*signed(data), '4.7.0', folder)
    assert asset['name'] == 'Rylume-4.7.0-Windows-x64.zip'


def test_old_latest_or_resource_release_cannot_pass_publication_gate(release):
    data, signed, folder = release
    for tag in ('v4.5.2', 'resource-packs-v1'):
        data['tag_name'] = tag
        with pytest.raises(DeliveryError, match='预期正式版本'):
            validate_release(*signed(data), '4.7.0', folder)


def test_source_only_release_and_missing_installer_fail(release):
    data, signed, folder = release
    data['assets'] = [{'name': 'Rylume-4.7.0-source.zip'}]
    with pytest.raises(DeliveryError, match='Windows 安装包'):
        validate_release(*signed(data), '4.7.0', folder)


def test_changed_installer_or_invalid_signature_fail(release):
    data, signed, folder = release
    raw, sig = signed(data)
    with pytest.raises(DeliveryError, match='签名'):
        validate_release(raw+b' ', sig, '4.7.0', folder)
    (folder/data['assets'][0]['name']).write_bytes(b'other installer')
    with pytest.raises(DeliveryError, match='本次安装包'):
        validate_release(raw, sig, '4.7.0', folder)
