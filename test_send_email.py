import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv('SMTP_HOST') or 'smtp.gmail.com'
SMTP_PORT = int(os.getenv('SMTP_PORT') or 587)
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
FROM_ADDR = os.getenv('OTP_EMAIL_FROM') or SMTP_USER
TO_ADDR = 'karthicksaravanan0703@gmail.com'

msg = MIMEText('This is a test OTP email from PEFR Titration Tracker. If you receive it, SMTP is working.')
msg['Subject'] = 'Test OTP Email'
msg['From'] = FROM_ADDR
msg['To'] = TO_ADDR

print('Using SMTP:', SMTP_HOST, SMTP_PORT, SMTP_USER)
try:
    s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
    s.ehlo()
    if SMTP_PORT == 587:
        s.starttls()
        s.ehlo()
    s.login(SMTP_USER, SMTP_PASS)
    s.sendmail(FROM_ADDR, [TO_ADDR], msg.as_string())
    s.quit()
    print('Email sent successfully to', TO_ADDR)
except Exception as e:
    print('Failed to send email:', e)
    raise
