from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import upgrade_ccnode_https as migration


def test_news_production_default_is_https():
    config = Path(__file__).resolve().parents[2] / 'config/news/broadcast.json'
    assert json.loads(config.read_text(encoding='utf-8'))['model']['codexBaseUrl'] == migration.NEW_URL


def test_json_upgrade_preserves_models_auth_and_other_endpoints():
    source = {'providers': {'openai-codex': {'baseUrl': migration.OLD_URL,
              'apiKey': {'source': 'file', 'id': '/providers/openaiCodex/apiKey'}}},
              'primary': 'openai-codex/gpt-5.3-codex-spark',
              'fallbacks': ['openai-codex/qwen'],
              'embedding': 'http://ccnode.briconbric.com:22545/v1',
              'unrelated': 'http://ccnode.briconbric.com:495300/v1',
              'url': migration.OLD_URL + '/chat/completions'}
    actual = migration.upgrade_json(source)
    assert actual['providers']['openai-codex']['baseUrl'] == migration.NEW_URL
    assert actual['url'] == migration.NEW_URL + '/chat/completions'
    for key in ('primary', 'fallbacks', 'embedding', 'unrelated'):
        assert actual[key] == source[key]
    assert actual['providers']['openai-codex']['apiKey'] == source['providers']['openai-codex']['apiKey']
    assert source['providers']['openai-codex']['baseUrl'] == migration.OLD_URL
    assert migration.upgrade_json(actual) == actual


def test_env_changes_only_base_urls_preserving_comments_and_private_values():
    source = ('# ' + migration.OLD_URL + '\n'
              'NEWS_CODEX_BASE_URL="' + migration.OLD_URL + '"\n'
              'export OPENCLAW_INTENT_FALLBACK_BASE_URL=' + migration.OLD_URL + '\n'
              'API_KEY=private-test-value\n'
              'OPENCLAW_MEMORY_EMBEDDING_BASE_URL=http://ccnode.briconbric.com:22545/v1\n')
    actual = migration.upgrade_env(source)
    assert actual.startswith('# ' + migration.OLD_URL + '\n')
    assert 'NEWS_CODEX_BASE_URL="' + migration.NEW_URL + '"\n' in actual
    assert 'export OPENCLAW_INTENT_FALLBACK_BASE_URL=' + migration.NEW_URL in actual
    assert 'API_KEY=private-test-value\n' in actual
    assert '49530/v1' in actual and '22545/v1' in actual
    assert migration.upgrade_env(actual) == actual


def test_migration_dry_run_and_idempotent_apply(tmp_path):
    root = tmp_path / 'state'
    agent = root / 'agents/main/agent'
    agent.mkdir(parents=True)
    config = root / 'openclaw.json'
    config.write_text(json.dumps({'baseUrl': migration.OLD_URL, 'model': 'keep'}))
    (agent / 'models.json').write_text(config.read_text())
    env = tmp_path / 'openclaw.env'
    env.write_text('NEWS_CODEX_BASE_URL=' + migration.OLD_URL + '\n')
    guard = tmp_path / 'guard.sh'
    guard.write_text('#!/bin/bash\nURL="' + migration.OLD_URL + '"\n')
    args = {'roots': (root,), 'env_path': env, 'guard_path': guard}
    assert len(migration.migrate(**args)['changed_files']) == 4
    assert migration.OLD_URL in config.read_text()
    originals = {path: path.read_text() for path in (config, agent / 'models.json', env, guard)}
    with patch.object(migration.os, 'chown', create=True), patch.object(migration.os, 'fchown', create=True), patch.object(migration.os, 'fchmod', create=True):
        assert len(migration.migrate(**args, apply=True)['changed_files']) == 4
        assert migration.migrate(**args, apply=True)['changed_files'] == []
    assert json.loads(config.read_text()) == {'baseUrl': migration.NEW_URL, 'model': 'keep'}
    for path, original in originals.items():
        backups = list(path.parent.glob(path.name + '.bak-https-*'))
        assert len(backups) == 1 and backups[0].read_text() == original
    assert not list(tmp_path.rglob('.*-*'))
