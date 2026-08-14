import urllib.request
import json
import time
import uuid

# 1. Create Case
req = urllib.request.Request('http://localhost:8000/cases/', data=json.dumps({'title': 'Smoke Test', 'description': 'Testing OCR'}).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as f:
        res = json.loads(f.read().decode('utf-8'))
        case_id = res['id']
        print('Created case:', case_id)
except Exception as e:
    print('Error creating case:', e)
    if hasattr(e, 'read'): print(e.read().decode())
    exit(1)

# 2. Upload PDF
import mimetypes
import os

pdf_path = "backend/data/EETT MATERIALES DE OFICINA - DIRECCIÓN.pdf"
boundary = uuid.uuid4().hex
headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}

with open(pdf_path, 'rb') as f:
    pdf_content = f.read()

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="EETT.pdf"\r\n'
    f'Content-Type: application/pdf\r\n\r\n'
).encode() + pdf_content + f'\r\n--{boundary}--\r\n'.encode()

print("Uploading PDF...")
req = urllib.request.Request(f'http://localhost:8000/cases/{case_id}/requirement/upload', data=body, headers=headers)
try:
    with urllib.request.urlopen(req) as f:
        res = json.loads(f.read().decode('utf-8'))
        print('Uploaded:', res)
except Exception as e:
    print('Error uploading:', e)
    if hasattr(e, 'read'): print(e.read().decode())
    
