import requests, json
BASE = 'http://127.0.0.1:8000'

doctor = {'username':'jandajanda0709@gmail.com','password':'Abc@1234'}
patient = {'username':'karticksaravanan0703@gmail.com','password':'Abc@1234'}

s = requests.Session()
print('Logging in doctor...')
resp = s.post(f'{BASE}/auth/login', data=doctor)
print(resp.status_code, resp.text)
if resp.status_code!=200:
    raise SystemExit('Doctor login failed')
token = resp.json()['access_token']
headers = {'Authorization':f'Bearer {token}'}

# find patient id by doctor patients list or assume patient id 3
print('Prescribing medication to patient id 3...')
med_payload = {'name':'Test Inhaler','dose':'2 puffs','schedule':'morning','days':7}
pr = s.post(f'{BASE}/doctor/patient/3/medication', json=med_payload, headers=headers)
print('Prescribe response:', pr.status_code, pr.text)
if pr.status_code!=200:
    print('Prescribe failed, aborting')
else:
    med = pr.json()
    med_id = med['id']
    print('Medication id:', med_id)

    # Now patient marks it taken
    print('Logging in patient...')
    resp2 = s.post(f'{BASE}/auth/login', data=patient)
    if resp2.status_code!=200:
        raise SystemExit('Patient login failed')
    ptoken = resp2.json()['access_token']
    pheaders = {'Authorization':f'Bearer {ptoken}'}

    take_payload = {'doses':1, 'notes':'Took as prescribed'}
    take_resp = s.post(f'{BASE}/medications/{med_id}/take', json=take_payload, headers=pheaders)
    print('Take response:', take_resp.status_code, take_resp.text)

    # Finally check doctor's notifications
    dnotes = s.get(f'{BASE}/notifications', headers=headers)
    print('Doctor notifications status:', dnotes.status_code)
    try:
        print(json.dumps(dnotes.json(), indent=2))
    except Exception as e:
        print('Could not parse doctor notifications:', e)
