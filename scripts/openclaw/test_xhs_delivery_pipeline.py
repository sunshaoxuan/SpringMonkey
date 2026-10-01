from __future__ import annotations
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import google_doc_delivery as delivery
import xhs_delivery_pipeline as pipeline
import install_xhs_delivery as installer
import cron_failure_self_heal as recovery
import recurring_cron_run_tool as manual
import xhs_source_probe as probe


def docx(text='draft', images=3):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive:
        archive.writestr('word/document.xml',f'<w:document xmlns:w="{delivery.W[1:-1]}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
        for i in range(images):
            archive.writestr(f'word/media/image{i}.png',bytes([i])*100)
    return stream.getvalue()


def test_export_requires_full_body_and_three_distinct_embedded_images():
    assert delivery.verify_export(docx(),docx())['body_verified']
    for actual in (docx('truncated'),docx(images=2)):
        with pytest.raises(ValueError):
            delivery.verify_export(docx(),actual)


def test_duplicate_embedded_images_are_rejected():
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as archive:
        archive.writestr('word/document.xml',f'<w:document xmlns:w="{delivery.W[1:-1]}"><w:t>draft</w:t></w:document>')
        for i in range(3):
            archive.writestr(f'word/media/image{i}.png',b'same')
    with pytest.raises(ValueError):
        delivery.verify_export(data.getvalue(),data.getvalue())


def test_export_rejects_hashtags_merged_into_one_paragraph():
    def tagged_document(merged):
        data=io.BytesIO()
        lines=['#first #second'] if merged else ['#first','#second']
        with zipfile.ZipFile(data,'w') as archive:
            paragraphs=''.join(f'<w:p><w:r><w:t>{line}</w:t></w:r></w:p>' for line in lines)
            archive.writestr('word/document.xml',f'<w:document xmlns:w="{delivery.W[1:-1]}"><w:body>{paragraphs}</w:body></w:document>')
            for i in range(3):archive.writestr(f'word/media/image{i}.png',bytes([i])*100)
        return data.getvalue()
    with pytest.raises(ValueError,match='one-tag-per-line'):
        delivery.verify_export(tagged_document(False),tagged_document(True))


def test_document_url_cannot_target_another_origin():
    assert delivery.document_id('https://docs.google.com/document/d/test/edit')=='test'
    for url in ('http://docs.google.com/document/d/test','https://evil.example/document/d/test','https://docs.google.com.evil.test/document/d/test'):
        with pytest.raises(ValueError): delivery.document_id(url)


def test_image_url_disallows_private_targets_and_plain_http():
    with patch.object(pipeline.socket,'getaddrinfo',return_value=[(0,0,0,'',('127.0.0.1',443))]):
        with pytest.raises(ValueError): pipeline.validate_public_url('https://localhost/image')
    with pytest.raises(ValueError): pipeline.validate_public_url('http://example.com/image')
    with pytest.raises(ValueError): pipeline.validate_public_url('https://user:pass@example.com/image')


def test_source_probe_never_exposes_private_google_or_account_pages():
    with patch.object(probe,'validate_public_url',side_effect=lambda url:url):
        for url in ('https://docs.google.com/document/d/private/edit','https://www.costco.co.jp/my-account/orders','https://example.com/source'):
            with pytest.raises(ValueError):probe.validate_source(url)
        assert probe.validate_source('https://www.costco.co.jp/product/p/123')
        assert probe.validate_source('https://public-cdn.example/image.jpg',image=True)


def test_manifest_image_claims_require_inspected_content_hash():
    payload={'product':'商品','title':'标题','body':'コストコ 商品说明','version':'JP-1','tags':['#商品'],
             'images':[{'kind':kind,'version':'JP-1','real':True,'no_watermark':True,'url':f'https://example.com/image-{i}',
                        'source':'https://example.com/source','sha256':'a'*64} for i,kind in enumerate(['official','official','real_photo'])]}
    with patch.object(pipeline,'validate_public_url',side_effect=lambda url:url):
        assert pipeline.validate_manifest(payload)
        payload['images'][0].pop('sha256')
        with pytest.raises(ValueError):pipeline.validate_manifest(payload)


def test_source_budget_preserves_product_images_before_navigation():
    images=[{'url':'https://example.com/'+str(i)+'x'*250,'alt':'product','w':1200,'h':1200} for i in range(8)]
    data={'title':'product','text':'x'*3200,'images':images.copy(),
          'links':[{'url':'https://example.com/'+'x'*300,'title':'navigation'} for _ in range(15)]}
    result=probe.compact_payload(data)
    assert result['images']==images
    assert len(result['links'])<15
    assert len(json.dumps(result,ensure_ascii=False))<=7000


def test_source_budget_remains_bounded_for_large_galleries_and_searches():
    for key in ('images','links'):
        data={'title':'source','text':'x'*3200,key:[{'url':'https://example.com/'+'x'*500} for _ in range(24)]}
        assert len(json.dumps(probe.compact_payload(data),ensure_ascii=False))<=7000


def test_search_filters_navigation_before_limiting_and_deduplicates():
    blocked=[{'url':f'https://google.com/navigation/{i}','title':'navigation'} for i in range(45)]
    product={'url':'https://www.costco.co.jp/c/product/p/123','title':'product'}
    with patch.object(probe,'validate_public_url',side_effect=lambda url:url):
        assert probe.source_links(blocked+[product,product])==[product]


def test_search_scope_matches_approved_public_sources_and_stays_bounded():
    query=probe.source_query('コストコ 購入品')
    assert query.startswith('コストコ 購入品 (')
    assert 'site:costco.co.jp' in query and 'site:ameblo.jp' in query
    assert set(probe.SEARCH_SITES)<=set(probe.SOURCE_DOMAINS)
    with pytest.raises(ValueError):probe.source_query('x'*201)


def test_public_image_download_uses_browser_identifier_without_credentials(tmp_path):
    from PIL import Image
    from unittest.mock import MagicMock
    import requests
    content=io.BytesIO()
    Image.new('RGB',(300,300),'red').save(content,format='PNG')
    response=MagicMock()
    response.__enter__.return_value=response
    response.is_redirect=False
    response.headers={'Content-Type':'image/png'}
    response.iter_content.return_value=[content.getvalue()]
    with patch.object(pipeline,'validate_public_url',side_effect=lambda url:url), patch.object(requests,'get',return_value=response) as get:
        digest=pipeline.fetch_image('https://example.com/photo.png',tmp_path/'photo.jpg')
    assert len(digest)==64
    assert get.call_args.kwargs['headers']=={'User-Agent':'Mozilla/5.0'}
    assert 'cookies' not in get.call_args.kwargs
    assert 'auth' not in get.call_args.kwargs
    assert get.call_args.kwargs['allow_redirects'] is False


def test_atomic_receipt_is_readable_and_replaces_previous(tmp_path):
    path=tmp_path/'receipt.json'
    delivery.atomic_json(path,{'status':'created'})
    delivery.atomic_json(path,{'status':'verified'})
    assert json.loads(path.read_text())=={'status':'verified'}
    assert len(list(tmp_path.iterdir()))==1


def test_recovery_catches_missed_failures_with_bounded_history():
    now=10_000_000
    task={'runtime':'cron','status':'failed','taskId':'one','label':'xhs','error':'overflow','endedAt':now-3600_000}
    assert recovery.parse_official_task_failures([task],{},now_ms=now)==[]
    assert len(recovery.parse_official_task_failures([task],{},max_age_seconds=604800,now_ms=now))==1
    task['endedAt']=now-604801_000
    assert recovery.parse_official_task_failures([task],{},max_age_seconds=604800,now_ms=now)==[]


def test_repeated_failures_retain_independent_task_identity():
    tasks=[{'runtime':'cron','status':'failed','taskId':str(i),'label':'xhs','error':'overflow','endedAt':10_000_000} for i in range(2)]
    events=recovery.parse_official_task_failures(tasks,{},now_ms=10_000_001)
    assert len({e['event_key'] for e in events})==2


def test_installer_reuses_git_pinned_dispatcher():
    source=installer.dispatcher_source()
    compile(source,'dispatcher','exec')
    assert 'failure-notification-failed' in source
    assert '--timeout 2400' in installer.DIRECT_LINE
    assert 'HOME=/var/lib/openclaw' in installer.DIRECT_LINE


def test_writer_initialization_is_idempotent_and_preserves_run_evidence(tmp_path):
    (tmp_path/'BOOTSTRAP.md').write_text('first conversation onboarding')
    (tmp_path/'AGENTS.md').write_text('starter instructions')
    (tmp_path/'manifest.json').write_text('research evidence')
    (tmp_path/'SOUL.md').write_text('existing soul')
    installer.initialize_writer_workspace(tmp_path)
    installer.initialize_writer_workspace(tmp_path)
    assert not (tmp_path/'BOOTSTRAP.md').exists()
    assert (tmp_path/'.setup-backup/BOOTSTRAP.md').read_text()=='first conversation onboarding'
    assert (tmp_path/'.setup-backup/AGENTS.md').read_text()=='starter instructions'
    assert 'unattended research worker' in (tmp_path/'AGENTS.md').read_text()
    assert 'Name: xhs-writer' in (tmp_path/'IDENTITY.md').read_text()
    assert (tmp_path/'manifest.json').read_text()=='research evidence'
    assert (tmp_path/'SOUL.md').read_text()=='existing soul'


def test_browser_guard_counts_pages_and_preserves_embedded_frames():
    fake_fcntl=SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=lambda *args:None)
    namespace={'__name__':'browser_guard_test'}
    with patch.dict(pipeline.sys.modules,{'fcntl':fake_fcntl}):
        exec(installer.browser_guard_source(),namespace)
    pages=[{'type':'page','id':'sentinel','url':'about:blank'}, {'type':'page','id':'document','url':'https://docs.google.com/document/d/test/edit'}]
    targets=pages+[{'type':'iframe','id':f'frame-{i}','url':'https://docs.google.com/drivesharing/driveshare'} for i in range(5)]
    closed=[]
    namespace.update(jget=lambda url:targets,get_chrome_rss_kb=lambda:0,close_target=closed.append)
    assert namespace['scan_browser']()==0
    assert closed==[]


def test_browser_guard_yields_to_active_document_lock(tmp_path):
    def busy(*args): raise BlockingIOError()
    fake_fcntl=SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=busy)
    namespace={'__name__':'browser_guard_test'}
    with patch.dict(pipeline.sys.modules,{'fcntl':fake_fcntl}):
        exec(installer.browser_guard_source(),namespace)
    namespace['Path']=lambda path:tmp_path/'lock'
    namespace['scan_browser']=lambda:pytest.fail('cleanup ran during active document operation')
    assert namespace['main']()==0


def test_direct_manual_trigger_works_without_obsolete_jobs_file(tmp_path):
    capabilities=tmp_path/'caps.json'
    capabilities.write_text(json.dumps({'jobs':[{'capability_id':'xhs','job_name':pipeline.JOB,'allow_manual_run':True,'executor':'direct_xhs_delivery','expected_delivery_channel_id':'private-channel'}]}))
    code,payload=manual.run_capability(text='run',capabilities_path=capabilities,jobs_path=tmp_path/'absent.json',dry_run=True,timeout=2400,capability_id='xhs')
    assert code==0 and payload['status']=='dry_run'
    assert 'private-channel' in payload['command']
    assert 'openclaw' not in payload['command']


def test_draft_failure_never_updates_latest_artifact(tmp_path):
    workspace=tmp_path/'workspace'
    flock=SimpleNamespace(LOCK_EX=1,LOCK_NB=2,flock=lambda *args:None)
    with patch.dict(pipeline.sys.modules,{'fcntl':flock}), patch.object(pipeline,'WORKSPACE',workspace), patch.object(pipeline,'configured_recipient',return_value='owner@example.com'), patch.object(pipeline,'prepare_manifest',side_effect=ValueError()) as research, patch.object(pipeline,'record_artifact') as registry, patch.object(pipeline.sys,'argv',['pipeline','--run-date','2026-10-01']):
        assert pipeline.main()==1
    research.assert_called_once()
    registry.assert_not_called()


def test_failed_research_manifest_is_not_reused_as_a_draft(tmp_path):
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    (workspace/'XHS_RECOMMENDATION_RULES.md').write_text('rules',encoding='utf-8')
    directory=workspace/'state/xhs-delivery/run'
    directory.mkdir(parents=True)
    (directory/'manifest.json').write_text(json.dumps({'status':'failed','reason':'insufficient evidence'}))
    with patch.object(pipeline,'WORKSPACE',workspace), patch.object(pipeline.subprocess,'run',return_value=SimpleNamespace(returncode=1)) as generation:
        with pytest.raises(ValueError,match='bounded product research'):
            pipeline.prepare_manifest(directory)
    generation.assert_called_once()
    assert json.loads((directory/'invalid-manifest.json').read_text())['status']=='failed'
    assert not (directory/'manifest.json').exists()
