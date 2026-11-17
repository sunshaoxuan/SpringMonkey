"""Verify the existing synthetic MoA run, without making further model calls."""
from pathlib import Path
import argparse
import hashlib
import json

QWEN = 'hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S'
EXPECTED = {
    'limit_mib': 3072,
    'plans': {
        'A': {'peak_mib': 400, 'seconds': 240, 'fits': True},
        'B': {'peak_mib': 4800, 'seconds': 20, 'fits': False},
    },
    'decision': 'A',
    'synthetic_data': True,
}


def read_jsonl(path):
    events = []
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
        except ValueError:
            pass
    return events


def message_text(messages):
    text = []
    for message in messages:
        content = message.get('content')
        if isinstance(content, str):
            text.append(content)
        elif isinstance(content, list):
            text.extend(x.get('text', '') for x in content if isinstance(x, dict))
    return '\n'.join(text)


def verify(trace_path, log_path, workspace):
    events = read_jsonl(log_path)
    result = [x for x in events if x.get('type') == 'result'][-1]
    assert result.get('exit_code') == 0
    uses = [x for x in events if x.get('type') == 'tool_use']
    reads = {x.get('input', {}).get('path') for x in uses if x.get('name') == 'read_file'}
    assert {'/workspace/moa-acceptance-result.json', '/workspace/moa-acceptance-summary.md'} <= reads
    assert [x.get('name') for x in uses].count('write_file') == 2
    assert not any(x.get('is_error') for x in events if x.get('type') == 'tool_result')
    traces = read_jsonl(trace_path)
    assert len(traces) == 1, 'user_turn cadence should fan out only once in this run'
    turn = traces[0]
    refs = turn['references']
    assert len(refs) == 2
    assert {x['model'] for x in refs} == {'deepseek-flash', QWEN}
    agg = turn['aggregator']
    assert agg['model'] == 'gpt-6.1-sol' and agg['provider'] == 'custom'
    injected = message_text(agg['input_messages'])
    rows = []
    for ref in refs:
        text = ref.get('output') or ''
        assert len(text.strip()) > 20 and not text.lstrip().startswith('[failed:')
        assert text.strip() != '(empty response)'
        assert text[:80] in injected, 'actual advisor output absent from aggregator request'
        usage = ref.get('usage') or {}
        assert usage.get('input_tokens', 0) + usage.get('output_tokens', 0) > 0
        rows.append({
            'model': ref['model'], 'provider': ref['provider'],
            'input_tokens': usage.get('input_tokens', 0),
            'output_tokens': usage.get('output_tokens', 0),
            'reasoning_tokens': usage.get('reasoning_tokens', 0),
            'output_chars': len(text),
            'output_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'actual_output_in_aggregator_input': True,
        })
    output = workspace / 'moa-acceptance-result.json'
    assert json.loads(output.read_text(encoding='utf-8')) == EXPECTED
    summary = workspace / 'moa-acceptance-summary.md'
    assert summary.stat().st_size > 100
    return {
        'status': 'PASS', 'agent_exit': 0, 'duration_ms': result.get('duration_ms'),
        'reference_fanouts': len(traces), 'references': rows,
        'aggregator': {'model': agg['model'], 'provider': agg['provider'],
                       'actual_reference_outputs_in_request': True,
                       'input_sha256': hashlib.sha256(injected.encode()).hexdigest()},
        'tool_calls': [x['name'] for x in uses], 'both_outputs_read_back': True,
        'decision': EXPECTED,
        'artifacts': {p.name: {'bytes': p.stat().st_size,
                             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in [output, summary]},
        'scope': 'one real MoA run with synthetic inputs; no general quality benchmark',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--agent-log', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, default=Path('/srv/hermes-pilot/workspace'))
    args = parser.parse_args()
    print(json.dumps(verify(args.trace, args.agent_log, args.workspace)))
