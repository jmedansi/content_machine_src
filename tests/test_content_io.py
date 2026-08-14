import pytest
import json
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lib import content_io

def test_read_meta():
    with tempfile.TemporaryDirectory() as tmp:
        meta_path = Path(tmp) / 'meta.json'
        data = {'account_id': '123', 'platform': 'facebook'}
        meta_path.write_text(json.dumps(data))
        result = content_io.read_meta(str(meta_path))
        assert result == data

def test_read_meta_missing():
    result = content_io.read_meta('/nonexistent')
    assert result is None

def test_atomic_write_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'test.json'
        data = {'key': 'value'}
        content_io.atomic_write_json(str(path), data)
        assert path.exists()
        result = json.loads(path.read_text())
        assert result == data

def test_checksum_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'file.txt'
        path.write_text('hello world')
        checksum = content_io.checksum_file(str(path))
        assert checksum is not None
        assert len(checksum) == 64  # SHA256 hex

def test_checksum_missing():
    checksum = content_io.checksum_file('/nonexistent')
    assert checksum is None

def test_scan_accounts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        acc1 = root / 'acc_123'
        acc1.mkdir()
        (acc1 / 'meta.json').write_text('{"platform": "twitter"}')
        acc2 = root / 'uuid-456'
        acc2.mkdir()
        results = content_io.scan_accounts(str(root))
        assert len(results) == 2
        assert any(r['account_id'] == 'acc_123' for r in results)
        assert any(r['account_id'] == 'uuid-456' for r in results)

def test_ensure_meta_fields():
    meta = {'existing': 'value'}
    defaults = {'default': 'def', 'existing': 'override'}
    result = content_io.ensure_meta_fields(meta, defaults)
    assert result['existing'] == 'value'  # meta overrides
    assert result['default'] == 'def'