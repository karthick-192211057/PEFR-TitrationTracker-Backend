import os
import json

try:
    import firebase_admin
    from firebase_admin import credentials, messaging
except Exception as e:
    firebase_admin = None
    messaging = None


def initialize():
    if firebase_admin is None:
        print("firebase_admin library not available; FCM disabled")
        return

    # allow using GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_ADMIN_CREDENTIALS
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("FIREBASE_ADMIN_CREDENTIALS")
    if not cred_path or not os.path.exists(cred_path):
        print("Firebase credentials not found; set GOOGLE_APPLICATION_CREDENTIALS or FIREBASE_ADMIN_CREDENTIALS environment variable")
        return

    try:
        cred = credentials.Certificate(cred_path)
        # initialize only once
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
            print("Firebase Admin initialized")
    except Exception as e:
        print("Failed to initialize Firebase Admin:", e)


def send_message_to_token(token: str, title: str, body: str, data: dict = None) -> bool:
    if not token:
        return False
    if messaging is None:
        # library not installed; just log
        print("FCM not available; would send to token:", token, title, body, data)
        return True

    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
            data=(data or {})
        )
        res = messaging.send(message)
        print("FCM sent: ", res)
        return True
    except Exception as e:
        print("FCM send failed:", e)
        return False


def send_messages_to_tokens(tokens: list, title: str, body: str, data: dict = None) -> dict:
    """Send to multiple tokens using multicast. Returns dict with successes and failures."""
    if not tokens:
        return {"success": 0, "failure": 0, "responses": []}
    if messaging is None:
        print("FCM not available; would send to tokens:", tokens)
        return {"success": len(tokens), "failure": 0, "responses": []}

    try:
        # Use send_each_for_multicast (supported in current firebase-admin)
        from firebase_admin import messaging as _messaging
        message = _messaging.MulticastMessage(
            notification=_messaging.Notification(title=title, body=body),
            tokens=tokens,
            data=(data or {})
        )
        resp = _messaging.send_each_for_multicast(message)
        results = []
        success_count = 0
        for idx, r in enumerate(resp.responses):
            # r.exception is set when a send failed
            err = getattr(r, 'exception', None)
            msg_id = getattr(r, 'message_id', None)
            success = err is None
            if success:
                success_count += 1
            results.append({
                "token": tokens[idx],
                "success": success,
                "response": msg_id,
                "error": str(err) if err else None
            })
        failure_count = len(tokens) - success_count
        return {"success": success_count, "failure": failure_count, "responses": results}
    except Exception as e:
        print("FCM multicast failed:", e)
        return {"success": 0, "failure": len(tokens), "error": str(e)}


# initialize on import (best-effort)
initialize()
