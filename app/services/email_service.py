"""Email service using Resend API for OTP delivery and notifications."""
import base64
import os
import requests
from app.config import Config


class EmailService:
    @staticmethod
    def _get_logo_data_uri():
        """Retrieve logo as base64 data URI so it renders locally and in email clients."""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logo_path = os.path.join(base_dir, 'static', 'img', 'logo.png')
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    return f"data:image/png;base64,{encoded}"
        except Exception:
            pass
        return "https://tgsims.com/static/img/logo.png"

    @classmethod
    def get_password_reset_html(cls, otp_code: str, username: str = "User") -> str:
        """Generate pixel-perfect HTML email matching the Tgsims OTP design."""
        logo_uri = cls._get_logo_data_uri()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Your Tgsims Verification Code</title>
</head>
<body style="margin: 0; padding: 32px 12px; background-color: #e9eef3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
  <!-- Outer Wrapper Card -->
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 440px; margin: 0 auto; background-color: #f3f6f9; border-radius: 16px; border: 1px solid #dce4ec; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04); overflow: hidden;">
    <!-- Top Header: Logo + App Name -->
    <tr>
      <td align="center" style="padding: 32px 24px 20px 24px;">
        <table role="presentation" border="0" cellspacing="0" cellpadding="0" style="margin: 0 auto;">
          <tr>
            <td align="center">
              <img src="{logo_uri}" width="46" height="52" alt="Tgsims" style="display: block; width: 46px; height: auto; border: 0; outline: none; margin: 0 auto 10px auto;">
            </td>
          </tr>
          <tr>
            <td align="center" style="font-size: 24px; font-weight: 700; color: #1e293b; letter-spacing: -0.3px; line-height: 1.2;">
              Tgsims
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Inner White Card -->
    <tr>
      <td style="padding: 0 20px 24px 20px;">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 12px; border: 1px solid #e8eef3; box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);">
          <tr>
            <td style="padding: 28px 24px 24px 24px;">
              <!-- Salutation -->
              <p style="margin: 0 0 14px 0; font-size: 15px; font-weight: 600; color: #0f172a; line-height: 1.4;">
                Hello {username},
              </p>

              <!-- Description -->
              <p style="margin: 0 0 22px 0; font-size: 14px; line-height: 1.55; color: #334155;">
                Use the verification code below to complete your password reset request. This code is valid for 10 minutes.
              </p>

              <!-- 6-Digit OTP Box (Click/Tap to select all for easy copying) -->
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="margin: 0 0 22px 0;">
                <tr>
                  <td align="center" style="background-color: #eaf4fb; border: 1.5px solid #bcdbf4; border-radius: 10px; padding: 18px 12px;">
                    <div title="Click or tap to copy code" style="font-size: 42px; font-weight: 700; color: #2372b0; letter-spacing: 5px; line-height: 1; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; cursor: pointer; -webkit-user-select: all; -moz-user-select: all; user-select: all;">
                      {otp_code}
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Warning text -->
              <p style="margin: 0 0 24px 0; font-size: 13px; line-height: 1.5; color: #1e293b;">
                Do not share this code. If you didn't request this, ignore this email.
              </p>

              <!-- Divider -->
              <hr style="border: none; border-top: 1px solid #e5e9ee; margin: 0 0 20px 0;">

              <!-- Footer info -->
              <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 500; color: #334155; text-align: center;">
                This is an automated notification from Tgsims.
              </p>
              <p style="margin: 0 0 12px 0; font-size: 13px; text-align: center;">
                <a href="https://tgsims.com/support" style="color: #2372b0; text-decoration: none; font-weight: 500;">[Contact Support]</a>
              </p>
              <p style="margin: 0; font-size: 12px; color: #475569; text-align: center;">
                &copy; 2026 Tgsims Inc. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
        return html

    @staticmethod
    def send_email(to_email, subject, html_content, text_content=None):
        """Send an email using Resend REST API."""
        api_key = Config.RESEND_API_KEY
        if not api_key:
            print("[EmailService] Warning: RESEND_API_KEY is not set in .env. Skipping email dispatch.")
            return {"success": False, "message": "RESEND_API_KEY is missing."}

        from_email = Config.RESEND_FROM_EMAIL or "Tgsims <noreply@tgsims.com>"
        payload = {
            "from": from_email,
            "to": [to_email] if isinstance(to_email, str) else to_email,
            "subject": subject,
            "html": html_content,
        }
        if text_content:
            payload["text"] = text_content

        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )
            data = response.json() if response.content else {}
            if response.status_code in (200, 201):
                return {"success": True, "data": data}
            else:
                print(f"[EmailService] Resend API error: {response.status_code} - {data}")
                return {"success": False, "error": data}
        except Exception as e:
            print(f"[EmailService] Failed to send email: {e}")
            return {"success": False, "error": str(e)}

    @classmethod
    def send_password_reset_otp(cls, to_email, otp_code, username="User"):
        """Send 6-digit OTP verification code matching the Tgsims email template."""
        subject = f"{otp_code} is your Tgsims verification code"
        html = cls.get_password_reset_html(otp_code, username)
        text = (
            f"Hello {username},\n\n"
            f"Use the verification code below to complete your password reset request. This code is valid for 10 minutes.\n\n"
            f"Verification Code: {otp_code}\n\n"
            f"Do not share this code. If you didn't request this, ignore this email.\n\n"
            f"This is an automated notification from Tgsims.\n"
            f"© 2026 Tgsims Inc. All rights reserved."
        )
        return cls.send_email(to_email, subject, html, text)
