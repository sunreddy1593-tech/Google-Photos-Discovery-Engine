"""Check a curated package in isolation, with external networking denied."""
import argparse
import hashlib
import json
import ipaddress
import os
from pathlib import Path
import sys
import socket
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package', type=Path, required=True)
args = parser.parse_args()
package = args.package.resolve()
audit = json.loads((package / 'package-audit.json').read_text(encoding='utf-8'))
for name, expected in audit['file_sha256'].items():
    assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected, name
assert not any((package / name).exists() for name in ('.env', '.git', 'data/gold', 'data/annotation', 'n8n'))
os.chdir(package)
sys.path[0] = str(package)
from streamlit.testing.v1 import AppTest

def forbidden(*args, **kwargs):
    raise AssertionError('Public demo attempted network access')

original_connect = socket.socket.connect

def local_runtime_connect(sock, address):
    # Windows asyncio uses a loopback socketpair to initialize its event loop.
    # Permit that local runtime traffic; external sockets and all HTTP fail.
    if isinstance(address, tuple) and ipaddress.ip_address(address[0]).is_loopback:
        return original_connect(sock, address)
    raise AssertionError('Public demo attempted external network access')

sections = (
    'Overview', 'Evidence browser', 'Problem comparison',
    'Reviewed reference evidence', 'Memory map and journeys',
    'Quality report', 'Ask the evidence', 'Methodology and limitations', 'Community insights',
)
with patch('socket.socket.connect', local_runtime_connect), patch('requests.get', forbidden), patch('requests.post', forbidden):
    app = AppTest.from_file(str(package / 'app.py'), default_timeout=30).run()
    assert not app.exception, app.exception
    for section in sections:
        app.segmented_control(key='section').set_value(section).run()
        assert not app.exception, (section, app.exception)
        if section == 'Quality report':
            assert any('extract/v4' in block.value for block in app.markdown)
            assert any('4 of 6' in block.value for block in app.markdown)
    app.segmented_control(key='section').set_value('Ask the evidence').run()
    app.text_input(key='ask_question').set_value('photo')
    app.button(key='ask_search').click().run()
    assert not app.exception
    assert any('Human-approved development reference label' in block.value for block in app.caption)
    app.text_input(key='ask_question').set_value('nevermatchingfixtureterm')
    app.button(key='ask_search').click().run()
    assert not app.exception
    assert any('insufficient evidence' in block.value for block in app.info)
print(json.dumps({'sections_checked': len(sections), 'provider_calls': 0, 'external_network_access': 'denied',
                  'public_records': audit['public_records'], 'reference_cases': audit['unique_reference_cases']}))
