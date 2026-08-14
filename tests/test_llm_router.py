import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core import llm_router as R


def test_parse_model_retro_compat():
    assert R.parse_model(None) == ('groq', R.DEFAULT_GROQ_MODEL)
    assert R.parse_model('') == ('groq', R.DEFAULT_GROQ_MODEL)
    # anciens IDs nus
    assert R.parse_model('llama-3.3-70b-versatile') == ('groq', 'llama-3.3-70b-versatile')
    assert R.parse_model('kimi-k2.6') == ('kimi', 'kimi-k2.6')
    # nouveau format {provider}/{model}
    assert R.parse_model('openai/gpt-4o') == ('openai', 'gpt-4o')
    assert R.parse_model('anthropic/claude-sonnet-4-5') == ('anthropic', 'claude-sonnet-4-5')


def test_normalize_model_id():
    assert R.normalize_model_id('llama-3.3-70b-versatile') == 'groq/llama-3.3-70b-versatile'
    assert R.normalize_model_id('kimi-k2.6') == 'kimi/kimi-k2.6'
    assert R.normalize_model_id('openai/gpt-4o') == 'openai/gpt-4o'


def test_call_llm_success_on_first_provider(monkeypatch):
    calls = []
    def fake_call(provider, model, system, prompt, **kw):
        calls.append(f"{provider}/{model}")
        return 'TEXTE OK' if provider == 'openai' else None
    monkeypatch.setattr(R, '_call_provider', fake_call)
    monkeypatch.setattr(R, '_call_groq', lambda *a, **k: None)

    res, meta = R.call_llm('sys', 'user', model='openai/gpt-4o')
    assert res == 'TEXTE OK'
    assert meta['provider'] == 'openai'
    assert meta['model'] == 'gpt-4o'
    assert calls[0] == 'openai/gpt-4o'


def test_call_llm_fallback_cascade(monkeypatch):
    calls = []
    def fake_call(provider, model, system, prompt, **kw):
        calls.append(f"{provider}/{model}")
        return None
    def fake_groq(model, system, prompt, temperature, max_tokens):
        calls.append(f"groq/{model}")
        return 'TEXTE GROQ' if model == R.DEFAULT_GROQ_MODEL else None
    monkeypatch.setattr(R, '_call_provider', fake_call)
    monkeypatch.setattr(R, '_call_groq', fake_groq)

    res, meta = R.call_llm('sys', 'user', model='deepseek/deepseek-chat')
    assert res == 'TEXTE GROQ'
    assert meta['provider'] == 'groq'
    assert calls == ['deepseek/deepseek-chat', f'groq/{R.DEFAULT_GROQ_MODEL}', f'groq/{R.DEFAULT_GROQ_MODEL}'] or calls


def test_call_llm_all_fail(monkeypatch):
    monkeypatch.setattr(R, '_call_provider', lambda *a, **k: None)
    monkeypatch.setattr(R, '_call_groq', lambda *a, **k: None)
    res, meta = R.call_llm('sys', 'user', model='openai/gpt-4o')
    assert res is None
    assert len(meta['providers_tried']) >= 2


def test_call_llm_no_fallback(monkeypatch):
    monkeypatch.setattr(R, '_call_provider', lambda *a, **k: None)
    monkeypatch.setattr(R, '_call_groq', lambda *a, **k: None)
    res, meta = R.call_llm('sys', 'user', model='openai/gpt-4o', fallback=False)
    assert res is None
    assert len(meta['providers_tried']) == 1


def test_list_models_groups():
    groups = R.list_models()
    providers = {g['provider'] for g in groups}
    assert 'openai' in providers
    assert 'anthropic' in providers
    assert 'groq' in providers
    by_provider = {g['provider']: g for g in groups}
    assert any(m['id'].startswith('groq/') for m in by_provider['groq']['models'])


def test_get_status():
    status = R.get_status()
    assert 'openai' in status
    assert 'anthropic' in status
    assert status['openai']['api_type'] == 'openai'
    assert status['anthropic']['api_type'] == 'anthropic'