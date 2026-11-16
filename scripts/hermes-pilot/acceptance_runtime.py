"""Local acceptance inside the authorized pilot container, using synthetic inputs."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

OUT=Path('/workspace/acceptance')
OUT.mkdir(exist_ok=True)

def alternatives():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    def call(name,url,model,key):
        payload={'model':model,'messages':[{'role':'user','content':'Reply exactly HERMES_MODEL_OK.'}],
                 'stream':False,'max_tokens':512,'reasoning_effort':'none'}
        request=urllib.request.Request(url+'/chat/completions',data=json.dumps(payload).encode(),
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        started=time.monotonic()
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            with opener.open(request,timeout=90) as response:
                body=json.loads(response.read(2_000_000))
                choice=body.get('choices',[{}])[0];text=choice.get('message',{}).get('content') or ''
                return {'route':name,'http_status':response.status,'model':body.get('model'),
                        'content_present':bool(text),'marker_match':'HERMES_MODEL_OK' in text,
                        'finish_reason':choice.get('finish_reason'),'seconds':round(time.monotonic()-started,2)}
        except urllib.error.HTTPError as exc:
            return {'route':name,'http_status':exc.code,'seconds':round(time.monotonic()-started,2)}
        except Exception as exc:
            return {'route':name,'error_class':type(exc).__name__,'seconds':round(time.monotonic()-started,2)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(call,'deepseek','https://api.deepseek.com','deepseek-flash',os.environ['HERMES_DEEPSEEK_API_KEY']),
              pool.submit(call,'qwen','https://ccnode.briconbric.com:49530/v1','hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ3_S',os.environ['HERMES_GATEWAY_API_KEY'])]
        result=[f.result() for f in jobs]
    (OUT/'models.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

def documents():
    from reportlab.pdfgen import canvas
    from docx import Document
    from openpyxl import Workbook,load_workbook
    from pptx import Presentation
    fixture=Path('/workspace/fixtures');fixture.mkdir(exist_ok=True)
    pdf=fixture/'sample.pdf';c=canvas.Canvas(str(pdf));c.drawString(72,720,'HERMES_PDF_SAMPLE 2026-11-17');c.save()
    extracted=subprocess.run(['/opt/hermes/.venv/bin/python','/opt/data/skills/productivity/pdf/scripts/pdf_read.py',str(pdf),'--text'],capture_output=True,text=True,timeout=30)
    document=Document();document.add_paragraph('HERMES_DOCX_SAMPLE');document.save(fixture/'sample.docx')
    workbook=Workbook();workbook.active['A1']='HERMES_XLSX_SAMPLE';workbook.save(fixture/'sample.xlsx')
    slides=Presentation();slide=slides.slides.add_slide(slides.slide_layouts[0]);slide.shapes.title.text='HERMES_PPTX_SAMPLE';slides.save(fixture/'sample.pptx')
    result={'pdf_text':extracted.returncode==0 and 'HERMES_PDF_SAMPLE' in extracted.stdout,
      'docx_readback':Document(fixture/'sample.docx').paragraphs[0].text=='HERMES_DOCX_SAMPLE',
      'xlsx_readback':load_workbook(fixture/'sample.xlsx').active['A1'].value=='HERMES_XLSX_SAMPLE',
      'pptx_readback':Presentation(fixture/'sample.pptx').slides[0].shapes.title.text=='HERMES_PPTX_SAMPLE',
      'synthetic_data':True,'visual_rendering_tested':False}
    (OUT/'documents.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['alternatives','documents'])
    args=parser.parse_args();globals()[args.action]()
