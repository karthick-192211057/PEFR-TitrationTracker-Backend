import requests, json
BASE = 'http://127.0.0.1:8000'

patient = {'username':'karticksaravanan0703@gmail.com','password':'Abc@1234'}
doctor = {'username':'jandajanda0709@gmail.com','password':'Abc@1234'}

s = requests.Session()
print('Logging in patient...')
resp = s.post(f'{BASE}/auth/login', data=patient)
print(resp.status_code, resp.text)
if resp.status_code!=200:
    raise SystemExit('Patient login failed')
token = resp.json()['access_token']
headers = {'Authorization':f'Bearer {token}'}

print('Posting PEFR record...')
pefr_payload = {'pefr_value': 150, 'source':'manual'}
pr = s.post(f'{BASE}/pefr/record', json=pefr_payload, headers=headers)
print('PEFR result:', pr.status_code, pr.text)

print('Now log in as doctor to inspect notifications...')
resp2 = s.post(f'{BASE}/auth/login', data=doctor)
print(resp2.status_code, resp2.text)
if resp2.status_code!=200:
    raise SystemExit('Doctor login failed')
dtoken = resp2.json()['access_token']
dheaders = {'Authorization':f'Bearer {dtoken}'}
notes = s.get(f'{BASE}/notifications', headers=dheaders)
print('Doctor notifications:', notes.status_code)
try:
    print(json.dumps(notes.json(), indent=2))
except Exception as e:
    print('Could not parse notifications:', e)
