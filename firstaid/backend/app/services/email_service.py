import aiosmtplib
from email.message import EmailMessage
from app.config import settings
from datetime import datetime

async def send_appointment_confirmation(patient_email: str, appointment_details: dict):
    """
    Sends an appointment confirmation email to the patient.
    """
    if not settings.EMAIL_USER or not settings.EMAIL_PASS:
        print("[EmailService] SMTP credentials missing, skipping email.")
        return

    # Format time for better readability
    raw_time = appointment_details.get('appointment_time')
    formatted_time = raw_time
    if isinstance(raw_time, str):
        try:
            dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            formatted_time = dt.strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            pass

    msg = EmailMessage()
    msg["Subject"] = f"Confirmation: Your Appointment with {appointment_details['doctor_name']}"
    msg["From"] = settings.EMAIL_USER
    msg["To"] = patient_email

    # Plain text content
    content = f"""
Hello {appointment_details['patient_name']},

Your medical appointment has been successfully booked via MedAssist AI.

--- APPOINTMENT SUMMARY ---
Doctor:    {appointment_details['doctor_name']}
Specialty: {appointment_details['specialty']}
Location:  {appointment_details['location']}
Time:      {formatted_time}
Condition: {appointment_details['emergency_type']}

Patient Details:
Name:  {appointment_details['patient_name']}
Phone: {appointment_details['patient_phone']}

If you need to reschedule or cancel, please contact the clinic directly at the location above.

Stay safe,
MedAssist AI Team
"""
    msg.set_content(content)

    # HTML content for a premium look
    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f4f7f9; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e1e8ed;">
            <div style="text-align: center; margin-bottom: 25px;">
                <h2 style="color: #C8374A; margin: 0; font-size: 24px;">Appointment Confirmed</h2>
                <p style="color: #777; margin-top: 5px;">MedAssist AI First Aid Support</p>
            </div>
            
            <p>Hello <strong>{appointment_details['patient_name']}</strong>,</p>
            <p>Your medical appointment has been successfully scheduled. Below are your appointment details:</p>
            
            <div style="background-color: #f9fafb; padding: 20px; border-radius: 8px; margin: 25px 0; border: 1px solid #edf2f7;">
                <h3 style="margin-top: 0; border-bottom: 1px solid #e2e8f0; padding-bottom: 10px; color: #2d3748; font-size: 18px;">Booking Summary</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; color: #4a5568;"><strong>Doctor:</strong></td><td style="padding: 8px 0; font-weight: 500;">{appointment_details['doctor_name']}</td></tr>
                    <tr><td style="padding: 8px 0; color: #4a5568;"><strong>Specialty:</strong></td><td style="padding: 8px 0; font-weight: 500;">{appointment_details['specialty']}</td></tr>
                    <tr><td style="padding: 8px 0; color: #4a5568;"><strong>Location:</strong></td><td style="padding: 8px 0; font-weight: 500;">{appointment_details['location']}</td></tr>
                    <tr><td style="padding: 8px 0; color: #4a5568;"><strong>Scheduled Time:</strong></td><td style="padding: 8px 0; color: #3182ce; font-weight: 600;">{formatted_time}</td></tr>
                    <tr><td style="padding: 8px 0; color: #4a5568;"><strong>Condition:</strong></td><td style="padding: 8px 0; font-weight: 500;">{appointment_details['emergency_type']}</td></tr>
                </table>
            </div>
            
            <p style="font-size: 14px; color: #4a5568;">Please arrive 10 minutes early at the location mentioned above. If you need to reschedule or cancel, please contact the clinic as soon as possible.</p>
            
            <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 30px 0;" />
            <div style="text-align: center;">
                <p style="font-size: 12px; color: #a0aec0; margin: 0;">This is an automated system notification from MedAssist AI.</p>
                <p style="font-size: 12px; color: #a0aec0; margin: 5px 0 0;">Please do not reply to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            username=settings.EMAIL_USER,
            password=settings.EMAIL_PASS,
            use_tls=False,
            start_tls=True,
        )
        print(f"[EmailService] Confirmation email sent successfully to {patient_email}")
    except Exception as e:
        print(f"[EmailService] Failed to send email to {patient_email}: {str(e)}")

async def send_hospital_notification(appointment_details: dict):
    """
    Sends a notification email to the hospital with patient details.
    """
    if not settings.EMAIL_USER or not settings.EMAIL_PASS or not settings.HOSPITAL_EMAIL:
        print("[EmailService] SMTP credentials or hospital email missing, skipping notification.")
        return

    # Format time for better readability
    raw_time = appointment_details.get('appointment_time')
    formatted_time = raw_time
    if isinstance(raw_time, str):
        try:
            dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            formatted_time = dt.strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            pass

    msg = EmailMessage()
    msg["Subject"] = f"Action Required: New Appointment Booked - {appointment_details['patient_name']}"
    msg["From"] = settings.EMAIL_USER
    msg["To"] = settings.HOSPITAL_EMAIL

    # Plain text content
    content = f"""
New Appointment Notification

A new appointment has been booked via MedAssist AI.

--- PATIENT DETAILS ---
Name:  {appointment_details['patient_name']}
Phone: {appointment_details['patient_phone']}
Email: {appointment_details.get('patient_email', 'Not provided')}

--- APPOINTMENT DETAILS ---
Doctor:    {appointment_details['doctor_name']}
Specialty: {appointment_details['specialty']}
Time:      {formatted_time}
Condition: {appointment_details['emergency_type']}

Please ensure the medical team is prepared for this appointment.

MedAssist AI System
"""
    msg.set_content(content)

    # HTML content for hospital staff
    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f4f7f9; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 2px solid #C8374A;">
            <div style="background-color: #C8374A; color: #ffffff; padding: 15px; border-radius: 8px 8px 0 0; margin: -30px -30px 25px -30px; text-align: center;">
                <h2 style="margin: 0; font-size: 22px;">New Appointment Notification</h2>
            </div>
            
            <p>A new appointment has been successfully booked via the <strong>MedAssist AI Chatbot</strong>.</p>
            
            <div style="display: flex; gap: 20px; margin: 25px 0;">
                <div style="flex: 1; background-color: #f9fafb; padding: 15px; border-radius: 8px; border: 1px solid #edf2f7;">
                    <h3 style="margin-top: 0; border-bottom: 2px solid #C8374A; padding-bottom: 8px; color: #2d3748; font-size: 16px;">Patient Information</h3>
                    <p style="margin: 8px 0;"><strong>Name:</strong> {appointment_details['patient_name']}</p>
                    <p style="margin: 8px 0;"><strong>Phone:</strong> {appointment_details['patient_phone']}</p>
                    <p style="margin: 8px 0;"><strong>Email:</strong> {appointment_details.get('patient_email', 'Not provided')}</p>
                </div>
            </div>

            <div style="background-color: #f0f7ff; padding: 15px; border-radius: 8px; border: 1px solid #c3dafe; margin-bottom: 25px;">
                <h3 style="margin-top: 0; border-bottom: 2px solid #3182ce; padding-bottom: 8px; color: #2c5282; font-size: 16px;">Appointment Details</h3>
                <table style="width: 100%;">
                    <tr><td style="padding: 5px 0;"><strong>Physician:</strong></td><td>{appointment_details['doctor_name']}</td></tr>
                    <tr><td style="padding: 5px 0;"><strong>Department:</strong></td><td>{appointment_details['specialty']}</td></tr>
                    <tr><td style="padding: 5px 0;"><strong>Scheduled For:</strong></td><td style="color: #2c5282; font-weight: 600;">{formatted_time}</td></tr>
                    <tr><td style="padding: 5px 0;"><strong>Type:</strong></td><td>{appointment_details['emergency_type']}</td></tr>
                </table>
            </div>
            
            <p style="font-size: 14px; font-weight: 500; color: #2d3748; background-color: #fffaf0; padding: 10px; border-radius: 6px; border: 1px solid #feebc8;">
                ⚠️ Action Required: Please review these details and update the internal hospital management system.
            </p>
            
            <hr style="border: 0; border-top: 1px solid #edf2f7; margin: 30px 0;" />
            <div style="text-align: center;">
                <p style="font-size: 11px; color: #a0aec0; margin: 0;">MedAssist AI Automation Service · Internal Use Only</p>
            </div>
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_SERVER,
            port=settings.SMTP_PORT,
            username=settings.EMAIL_USER,
            password=settings.EMAIL_PASS,
            use_tls=False,
            start_tls=True,
        )
        print(f"[EmailService] Hospital notification sent to {settings.HOSPITAL_EMAIL}")
    except Exception as e:
        print(f"[EmailService] Failed to send hospital notification: {str(e)}")
