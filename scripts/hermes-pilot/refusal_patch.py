"""Prepare a hash-bound local patch for Hermes v0.23.1. Never downloads or deploys."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

COMMIT = '3b421578588243f920886e6fe79a6faa87ea026e'
FILES = {
    'agent/chat_completion_helpers.py': 'NousResearch__hermes-agent__agent__chat_completion_helpers.py',
    'agent/turn_truncation.py': 'NousResearch__hermes-agent__agent__turn_truncation.py',
}

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def transform(path: str, text: str) -> str:
    if path.endswith('chat_completion_helpers.py'):
        marker = '    from agent.fallback_cooldown import _arm_rate_limit_cooldown, switch_deferred_by_reset\n'
        guard = ('    # SpringMonkey pilot: policy refusals remain terminal across all fallback callers.\n'
                 '    if getattr(reason, "value", reason) in {"content_policy_blocked", "provider_policy_blocked"}:\n'
                 '        return False\n')
        if text.count(marker) != 1:
            raise ValueError('unexpected fallback entry point')
        return text.replace(marker, guard + marker, 1)
    start = text.index('    if agent._has_pending_fallback():', text.index('def handle_content_policy_refusal('))
    end = text.index('    agent._flush_status_buffer()', start)
    old = text[start:end]
    if '_try_activate_fallback(reason=FailoverReason.content_policy_blocked)' not in old:
        raise ValueError('unexpected refusal branch')
    text = text[:start] + '    # SpringMonkey pilot: return the original refusal without provider switching.\n\n' + text[end:]
    text = text.replace('    Deterministic for the unchanged prompt — never retried: one configured-fallback try,\n'
                        '    else surface the refusal (explanation may live only in the reasoning channel).',
                        '    Surface the refusal without retry or fallback; preserve the original explanation.')
    text = text.replace('    from agent.conversation_loop import _arm_fallback_restart, _content_policy_blocked_result\n',
                        '    from agent.conversation_loop import _content_policy_blocked_result\n')
    text = text.replace('    # block (``end_turn``); both arrive here as content_filter. Logged before the fallback try so a\n'
                        '    # refusal the fallback answers still leaves its cause in agent.log (#124874).',
                        '    # block (``end_turn``); both arrive here as content_filter. Preserve the cause in the log.')
    return text

def prepare(source: Path, output: Path, expected: dict[str, str]) -> dict:
    if output.exists():
        raise ValueError('output must be a new directory')
    prepared = []
    diff = []
    for path, filename in FILES.items():
        data = (source / filename).read_bytes()
        if sha(data) != expected[path]:
            raise ValueError('pinned source mismatch: ' + path)
        original = data.decode('utf-8')
        changed = transform(path, original)
        compile(changed, path, 'exec')
        prepared.append((path, data, changed.encode('utf-8')))
        diff.extend(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                         fromfile='a/' + path, tofile='b/' + path, n=0))
    output.mkdir(parents=True)
    manifest = {'upstream_commit': COMMIT, 'files': []}
    for path, before, after in prepared:
        dest = output / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(after)
        manifest['files'].append({'path': path, 'before_sha256': sha(before), 'after_sha256': sha(after)})
    patch = ''.join(diff).encode('utf-8')
    (output / 'refusal-terminal.patch').write_bytes(patch)
    manifest['patch_sha256'] = sha(patch)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pins = json.loads(Path(__file__).with_name('upstream-pins.json').read_text(encoding='utf-8'))
    print(json.dumps(prepare(args.source, args.output, pins['sha256']), indent=2))
