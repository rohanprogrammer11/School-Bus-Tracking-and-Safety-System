import smtplib
from email.message import EmailMessage

def send_otp_email(to_email, otp):
    try:
        msg = EmailMessage()
        msg["Subject"] = "School Bus Safety - Email Verification OTP"
        msg["From"] = "schoolbustracking000@gmail.com"
        msg["To"] = to_email

        msg.set_content(f"""
Hello,

Your OTP for Driver Account Verification is:

{otp}

This OTP is valid for 5 minutes.

If you did not request this, please ignore this email.
""")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("schoolbustracking000@gmail.com", "fohu hszp uqpq axng")
            server.send_message(msg)

        print("✅ OTP Email Sent Successfully")

    except Exception as e:
        print("❌ Email Sending Failed:", e)
        raise
