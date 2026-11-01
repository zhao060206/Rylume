"""Check the public update channel used by existing Windows installations.

Run after uploading all artifacts to a draft, then again with --latest after
publishing. A source push or a resource-pack release is not an application
release. This command reads public endpoints and never needs an API token.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from github_delivery import DeliveryError, GitHubDelivery, REPOSITORY, trusted_url, version_tuple
from product_identity import PRODUCT_VERSION
from update_mirrors import verify_manifest


def validate_release(raw, signature, expected_version, artifacts=None):
    version_tuple(expected_version)
    verify_manifest(raw, signature)
    data = json.loads(raw)
    if data.get('tag_name') != 'v' + expected_version or data.get('draft') or data.get('prerelease'):
        raise DeliveryError('公开更新通道未指向预期正式版本')
    name = f'Rylume-{expected_version}-Windows-x64.zip'
    matches = [a for a in data.get('assets', []) if a.get('name') == name]
    if len(matches) != 1:
        raise DeliveryError('更新清单缺少唯一的 Windows 安装包')
    asset = matches[0]
    expected_url = f'https://github.com/{REPOSITORY}/releases/download/v{expected_version}/{name}'
    trusted_url(asset.get('browser_download_url', ''))
    if asset['browser_download_url'] != expected_url:
        raise DeliveryError('安装包地址与版本不一致')
    if type(asset.get('size')) is not int or not 0 < asset['size'] < 1024**3:
        raise DeliveryError('安装包大小无效')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', str(asset.get('digest', ''))):
        raise DeliveryError('安装包缺少 SHA-256 校验值')
    if artifacts is not None:
        archive = Path(artifacts) / name
        with archive.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if archive.stat().st_size != asset['size'] or 'sha256:' + digest != asset['digest']:
            raise DeliveryError('公开更新清单与本次安装包不一致')
    return asset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default=PRODUCT_VERSION)
    parser.add_argument('--artifacts', type=Path)
    parser.add_argument('--latest', action='store_true', help='Check the channel used by installed clients')
    args = parser.parse_args()
    delivery = GitHubDelivery()
    segment = 'latest/download' if args.latest else 'download/v' + args.version
    base = f'https://github.com/{REPOSITORY}/releases/{segment}'
    raw = delivery.read(base + '/update.json', limit=128*1024)
    signature = delivery.read(base + '/update.json.sig', limit=1024)
    asset = validate_release(raw, signature, args.version, args.artifacts)
    # Follow the real public download route and check the declared file size.
    # Streaming avoids downloading a second full installer during this gate.
    with delivery.response(asset['browser_download_url'], stream=True) as response:
        if int(response.headers.get('Content-Length', 0)) != asset['size']:
            raise DeliveryError('公开安装包不可下载或文件大小不一致')
    print(json.dumps({'passed': True, 'version': args.version,
                      'channel': 'latest' if args.latest else 'versioned',
                      'installer': asset['name'], 'bytes': asset['size'],
                      'signature_verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
