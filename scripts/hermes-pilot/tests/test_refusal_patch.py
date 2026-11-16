import ast
from contextlib import suppress
from dataclasses import dataclass
import enum
import importlib.util
import json
import logging
import shutil
import subprocess
from pathlib import Path
import sys
import types

import pytest

from refusal_patch import FILES, prepare, sha, transform

@pytest.fixture
def source(request):
    value=request.config.getoption('--hermes-source')
    if not value:pytest.fail('--hermes-source is required; refusal tests must not silently skip')
    return Path(value)

@pytest.fixture
def classifier(source,monkeypatch):
    path=source/'NousResearch__hermes-agent__agent__error_classifier.py'
    spec=importlib.util.spec_from_file_location('fixture_error_classifier',path)
    module=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,spec.name,module)
    spec.loader.exec_module(module)
    return module

def extract(text,names,namespace,monkeypatch):
    module=types.ModuleType('fixture_hermes_functions')
    module.__dict__.update(namespace)
    monkeypatch.setitem(sys.modules,module.__name__,module)
    tree=ast.parse(text)
    statements=[ast.parse('from __future__ import annotations').body[0]]
    statements += [n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert len(statements)==len(names)+1
    exec(compile(ast.fix_missing_locations(ast.Module(body=statements,type_ignores=[])),'fixed_hermes_source','exec'),module.__dict__)
    return module

@pytest.fixture
def dependencies(monkeypatch):
    events=[]
    def install(name,**values):
        m=types.ModuleType(name);m.__dict__.update(values);monkeypatch.setitem(sys.modules,name,m)
    def bind(agent,fb,provider,model):
        old=agent.model,agent.provider
        agent.model,agent.provider=model,provider
        return old
    install('agent',__path__=[])
    install('agent.fallback_cooldown',switch_deferred_by_reset=lambda *a:False,_arm_rate_limit_cooldown=lambda *a,**kw:None)
    install('agent.route_binding',bind_route_entry=bind)
    install('agent.native_compaction',resolve_native_compaction_capabilities=lambda **kw:{})
    install('hermes_cli',__path__=[])
    install('hermes_cli.observability',__path__=[])
    install('hermes_cli.observability.shared_metrics_events',record_fallback=lambda **kw:events.append(kw))
    install('agent.conversation_loop',_arm_fallback_restart=lambda *a:'restarted',
            _content_policy_blocked_result=lambda history,count,**kw:{'messages':history,'api_call_count':count,**kw})
    install('agent.turn_context',history_before_current_turn=lambda *a:[{'role':'user','content':'previous safe turn'}],
            refused_turn_boundary_row_id=lambda *a:7)
    return events

def fallback(source,classifier,monkeypatch,patched=True):
    text=(source/FILES['agent/chat_completion_helpers.py']).read_text(encoding='utf-8')
    if patched:text=transform('agent/chat_completion_helpers.py',text)
    ns={'FailoverReason':classifier.FailoverReason,'logger':logging.getLogger('fixture'),
        '_fallback_entry_key':lambda fb:fb['model'],'_should_skip_fallback_candidate':lambda *a:False,
        'rewrite_prompt_model_identity':lambda *a:None,'_fallback_reason_text':lambda r:str(r),
        '_buffer_fallback_notice':lambda *a:None,'_log_fallback_activated':lambda *a:None,
        '_reset_stale_streak':lambda *a:None,'_fallback_chain_exhausted':lambda *a:False}
    return extract(text,{'try_activate_fallback'},ns,monkeypatch).try_activate_fallback

def agent():
    return types.SimpleNamespace(_fallback_index=0,_fallback_chain=[{'provider':'custom','model':'backup'}],
        model='primary',provider='custom',base_url='https://fixture.invalid',_fallback_activated=False)

def test_prepatch_regression_reproduces_and_fixed_guard_stops(source,classifier,dependencies,monkeypatch):
    before=agent()
    assert fallback(source,classifier,monkeypatch,False)(before,classifier.FailoverReason.content_policy_blocked)
    assert before.model=='backup'
    after=agent()
    assert fallback(source,classifier,monkeypatch)(after,classifier.FailoverReason.content_policy_blocked) is False
    assert after.model=='primary' and after._fallback_index==0

@pytest.mark.parametrize('reason',['content_policy_blocked','provider_policy_blocked'])
@pytest.mark.parametrize('as_text',[False,True])
def test_policy_reasons_do_not_consume_candidate_or_bind_route(source,classifier,dependencies,monkeypatch,reason,as_text):
    run=fallback(source,classifier,monkeypatch);a=agent()
    value=reason if as_text else getattr(classifier.FailoverReason,reason)
    assert run(a,value) is False
    assert a.model=='primary' and a._fallback_index==0 and dependencies==[]

@pytest.mark.parametrize('reason',['rate_limit','overloaded','server_error','timeout'])
def test_availability_fallback_still_binds_real_function_path(source,classifier,dependencies,monkeypatch,reason):
    run=fallback(source,classifier,monkeypatch);a=agent()
    assert run(a,getattr(classifier.FailoverReason,reason)) is True
    assert a.model=='backup' and a._fallback_index==1 and len(dependencies)==1

@pytest.mark.parametrize('text,reason',[('refused text',None),('', 'reasoning refusal')])
def test_http200_refusal_returns_terminal_and_preserves_cleanup(source,classifier,dependencies,monkeypatch,text,reason):
    original=(source/FILES['agent/turn_truncation.py']).read_text(encoding='utf-8')
    patched=transform('agent/turn_truncation.py',original)
    events=[]
    ns={'FailoverReason':classifier.FailoverReason,'dataclass':dataclass,'suppress':suppress,
        'logger':logging.getLogger('fixture'),'normalize_response_for_agent':lambda a,r:r,
        'stop_thinking_spinner':lambda *a:events.append('spinner stopped'),
        'content_policy_copy':lambda **kw:kw['summary'],'provider_label_for':lambda p:p}
    module=extract(patched,{'RefusalVerdict','handle_content_policy_refusal'},ns,monkeypatch)
    a=agent();a.log_prefix='';a._session_db=None
    a._extract_reasoning=lambda r:reason
    a._invoke_api_request_error_hook=lambda **kw:events.append(kw)
    a._flush_status_buffer=lambda:events.append('flushed')
    a._emit_diagnostic_status=lambda s:events.append(s)
    a._cleanup_task_resources=lambda task:events.append(('cleanup',task))
    a._try_activate_fallback=lambda **kw:pytest.fail('HTTP200 handler must never ask for fallback')
    response=types.SimpleNamespace(content=text,provider_data={})
    result=module.handle_content_policy_refusal(a,response,None,thinking_spinner=None,messages=[],api_messages=[],
        api_kwargs={},active_system_prompt='original prompt',conversation_history=[],api_call_count=1,
        effective_task_id='fixture',turn_id=1,api_request_id='fixture',api_start_time=0,retry_count=0,max_retries=2)
    assert result.action=='return'
    assert (text or reason) in result.result['final_response']
    assert result.result['messages']==[{'role':'user','content':'previous safe turn'}]
    assert ('cleanup','fixture') in events
    assert any(isinstance(x,dict) and x['retryable'] is False for x in events)
    assert a.model=='primary' and a._fallback_index==0

def test_hash_pin_rejects_drift_and_outputs_applyable_patch(source,tmp_path):
    pins=json.loads((Path(__file__).parents[1]/'upstream-pins.json').read_text())['sha256']
    result=prepare(source,tmp_path/'candidate',pins)
    assert len(result['files'])==2
    patch=(tmp_path/'candidate/refusal-terminal.patch').read_text(encoding='utf-8')
    assert 'a/agent/chat_completion_helpers.py' in patch and 'a/agent/turn_truncation.py' in patch
    checkout=tmp_path/'checkout';checkout.mkdir()
    subprocess.run(['git','init','-q'],cwd=checkout,check=True,capture_output=True)
    for path,filename in FILES.items():
        target=checkout/path;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/filename,target)
    patch_path=str(tmp_path/'candidate/refusal-terminal.patch')
    # The target is Linux LF. Keep this fixture independent of Windows global autocrlf.
    subprocess.run(['git','-c','core.autocrlf=false','apply','--unidiff-zero','--check',patch_path],cwd=checkout,check=True,capture_output=True)
    subprocess.run(['git','-c','core.autocrlf=false','apply','--unidiff-zero',patch_path],cwd=checkout,check=True,capture_output=True)
    for row in result['files']:
        assert sha((checkout/row['path']).read_bytes())==row['after_sha256']
    bad=dict(pins);bad['agent/turn_truncation.py']='0'*64
    with pytest.raises(ValueError,match='mismatch'):prepare(source,tmp_path/'must-not-exist',bad)
    assert not (tmp_path/'must-not-exist').exists()
