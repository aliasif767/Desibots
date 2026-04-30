import aiosmtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import os

load_dotenv()

# Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
LAWYER_EMAIL = os.getenv("LAWYER_EMAIL", "asifali151519@gmail.com")

async def send_appointment_confirmation(user_email: str, booking_details: dict):
    """
    Sends an appointment confirmation email to the client.
    """
    if not EMAIL_USER or not EMAIL_PASS:
        print("[EmailService] SMTP credentials missing, skipping user email.")
        return

    msg = EmailMessage()
    msg["Subject"] = "Consultation Confirmed: Pakistan Law AI"
    msg["From"] = EMAIL_USER
    msg["To"] = user_email

    content = f"""
Hello {booking_details['name']},

Your legal consultation has been successfully scheduled.

--- CONSULTATION SUMMARY ---
Client Name:  {booking_details['name']}
Phone Number: {booking_details['phone']}
Role/Service: Legal Advice Request

If you need to reschedule, please reply to this email or contact our support.

Best regards,
Pakistan Law AI Team
"""
    msg.set_content(content)

    # HTML content
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 8px; border: 1px solid #ddd;">
            <div style="text-align: center; border-bottom: 2px solid #1a5f7a; padding-bottom: 10px; margin-bottom: 20px;">
                <h2 style="color: #1a5f7a; margin: 0;">Consultation Confirmed</h2>
            </div>
            <p>Hello <strong>{booking_details['name']}</strong>,</p>
            <p>Thank you for choosing Pakistan Law AI. Your consultation request has been received and scheduled.</p>
            <div style="background-color: #f0f7ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #1a5f7a;">Booking Details</h3>
                <p style="margin: 5px 0;"><strong>Name:</strong> {booking_details['name']}</p>
                <p style="margin: 5px 0;"><strong>Phone:</strong> {booking_details['phone']}</p>
                <p style="margin: 5px 0;"><strong>Status:</strong> Confirmed</p>
            </div>
            <p style="font-size: 14px; color: #666;">Our legal team will review your request and may contact you for further details.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;" />
            <p style="font-size: 11px; color: #999; text-align: center;">This is an automated notification from Pakistan Law AI.</p>
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_SERVER,
            port=SMTP_PORT,
            username=EMAIL_USER,
            password=EMAIL_PASS,
            use_tls=False,
            start_tls=True,
        )
        print(f"[EmailService] Confirmation email sent to {user_email}")
    except Exception as e:
        print(f"[EmailService] Failed to send email to {user_email}: {str(e)}")

async def send_lawyer_notification(booking_details: dict):
    """
    Sends a notification email to the lawyer with client details.
    """
    if not EMAIL_USER or not EMAIL_PASS or not LAWYER_EMAIL:
        print("[EmailService] SMTP credentials or lawyer email missing, skipping notification.")
        return

    msg = EmailMessage()
    msg["Subject"] = f"NEW CASE: Consultation Request from {booking_details['name']}"
    msg["From"] = EMAIL_USER
    msg["To"] = LAWYER_EMAIL

    content = f"""
New Case Notification

A new consultation has been booked via Pakistan Law AI.

--- CLIENT INFORMATION ---
Name:  {booking_details['name']}
Phone: {booking_details['phone']}
Email: {booking_details['email']}

--- NOTES ---
{booking_details.get('notes', 'No additional notes provided.')}

Please review the case details and follow up with the client.

Pakistan Law AI Automation
"""
    msg.set_content(content)

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; border: 2px solid #1a5f7a; padding: 20px; border-radius: 10px;">
            <h2 style="color: #1a5f7a; border-bottom: 2px solid #1a5f7a; padding-bottom: 10px;">New Consultation Request</h2>
            <p>Admin, a new client has requested legal guidance through the AI portal.</p>
            <div style="background-color: #f4f4f4; padding: 15px; border-radius: 5px;">
                <h3 style="margin-top: 0;">Client Details</h3>
                <p><strong>Name:</strong> {booking_details['name']}</p>
                <p><strong>Phone:</strong> {booking_details['phone']}</p>
                <p><strong>Email:</strong> {booking_details['email']}</p>
                <p><strong>Message:</strong> {booking_details.get('notes', 'N/A')}</p>
            </div>
            <p style="margin-top: 20px;"><strong>Action Required:</strong> Please contact the client within 24 hours.</p>
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_SERVER,
            port=SMTP_PORT,
            username=EMAIL_USER,
            password=EMAIL_PASS,
            use_tls=False,
            start_tls=True,
        )
        print(f"[EmailService] Lawyer notification sent to {LAWYER_EMAIL}")
    except Exception as e:
        print(f"[EmailService] Failed to send lawyer notification: {str(e)}")
