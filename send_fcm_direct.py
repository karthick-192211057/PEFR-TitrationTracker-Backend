import os
import firebase_admin
from firebase_admin import credentials, messaging

# Uses GOOGLE_APPLICATION_CREDENTIALS env var set earlier
cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if not cred_path or not os.path.exists(cred_path):
    print('FATAL: GOOGLE_APPLICATION_CREDENTIALS not set or file missing:', cred_path)
    raise SystemExit(1)

cred = credentials.Certificate(cred_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

# Paste the token here (from your device logcat)
TOKEN = "fZpEowrJQ66mTMqBJuKkyP:APA91bEAj0x41IG--XG3vTQHzLharpDEm2CAoEzvbjT3XOs0_CCveENqaq_KKT9J0BhCTDzrnW4ovRWMzFwDp_PR4SB7kfOx-HBxfa689UaCWDE-b6ItmCQ"

def send_test():
    try:
        message = messaging.Message(
            notification=messaging.Notification(title='Test Push', body='Hello from backend test'),
            token=TOKEN,
            data={'source': 'backend-test'}
        )
        res = messaging.send(message)
        print('FCM send response:', res)
    except Exception as e:
        print('FCM send error:', e)

if __name__ == '__main__':
    send_test()
