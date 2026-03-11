import imaplib
import email
import re
import os
import time
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER = os.environ.get("IMAP_SERVER")
IMAP_USER = os.environ.get("IMAP_USER")
IMAP_PASS = os.environ.get("IMAP_PASS")

def get_latest_amazon_otp(max_wait_seconds=60):
    if not IMAP_SERVER or not IMAP_USER or not IMAP_PASS:
        print("IMAP credentials not found in .env file.")
        return None
        
    print(f"Bağlanılıyor: {IMAP_SERVER} | Kullanıcı: {IMAP_USER}")
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait_seconds:
        try:
            # Connect to the server
            mail = imaplib.IMAP4_SSL(IMAP_SERVER)
            mail.login(IMAP_USER, IMAP_PASS)
            mail.select("inbox")
            
            # Search for unread emails from Amazon
            # Or just fetch the latest emails and check the sender and subject
            status, messages = mail.search(None, '(UNSEEN FROM "amazon")')
            
            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
                if email_ids:
                    # Get the most recent one
                    latest_email_id = email_ids[-1]
                    status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
                    
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes):
                                try:
                                    subject = subject.decode(encoding if encoding else "utf-8")
                                except:
                                    subject = str(subject)
                                    
                            print(f"Bulunan E-posta Başlığı: {subject}")
                            
                            # Extract body
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode()
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode()
                                
                            # Regex to find 6-digit code like "123456" or "123456" or "123 456"
                            match = re.search(r'\b(\d{6})\b', body)
                            if not match:
                                # sometimes they put it like 123 456
                                match = re.search(r'\b(\d{3})\s+(\d{3})\b', body)
                                if match:
                                    otp = match.group(1) + match.group(2)
                                    return otp
                            
                            if match:
                                return match.group(1)
            
            mail.logout()
        except Exception as e:
            print(f"E-posta okunurken hata oluştu: {e}")
            
        print(f"OTP Kodu Henüz Gelmedi... ({int(time.time() - start_time)}/{max_wait_seconds} sn)")
        time.sleep(5)
        
    print("Maksimum bekleme süresi doldu, yeni OTP kodu bulunamadı.")
    return None

if __name__ == "__main__":
    print("Testing OTP Reader...")
    code = get_latest_amazon_otp(max_wait_seconds=10)
    print(f"Extracted OTP: {code}")
