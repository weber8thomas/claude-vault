"""WebAuthn approval server for vault_set operations."""

import json
import os
import secrets
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass, asdict

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    AuthenticatorAttachment,
    PublicKeyCredentialDescriptor,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier


@dataclass
class PendingOperation:
    """Pending vault operation awaiting approval."""
    op_id: str
    service: str
    action: str  # CREATE or UPDATE
    secrets: Dict[str, str]
    warnings: list
    created_at: float
    approved: bool = False
    approved_at: Optional[float] = None


class ApprovalServer:
    """Manages pending operations and WebAuthn approvals."""

    def __init__(self, port: int = 8091, domain: str = "vault-approve.laboiteaframboises.duckdns.org", origin: str = "https://vault-approve.laboiteaframboises.duckdns.org"):
        self.port = port
        self.domain = domain  # rp_id for WebAuthn
        self.origin = origin  # Expected origin for WebAuthn
        self.app = FastAPI()
        self.pending_ops: Dict[str, PendingOperation] = {}
        self.credentials_db: Dict[str, dict] = {}  # user_id -> credential
        self.challenges: Dict[str, bytes] = {}  # session_id -> challenge

        # Storage paths
        self.storage_dir = Path.home() / ".claude-vault"
        self.storage_dir.mkdir(exist_ok=True)
        self.credentials_file = self.storage_dir / "webauthn-credentials.json"

        # Load existing credentials
        self._load_credentials()

        # Setup routes
        self._setup_routes()

        # Server thread
        self.server_thread = None

    def _load_credentials(self):
        """Load stored WebAuthn credentials."""
        if self.credentials_file.exists():
            try:
                data = json.loads(self.credentials_file.read_text())
                self.credentials_db = data
            except Exception as e:
                print(f"Warning: Could not load credentials: {e}")

    def _save_credentials(self):
        """Save WebAuthn credentials to disk."""
        try:
            self.credentials_file.write_text(json.dumps(self.credentials_db, indent=2))
        except Exception as e:
            print(f"Warning: Could not save credentials: {e}")

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/")
        async def index():
            """Server status page."""
            has_auth = len(self.credentials_db) > 0
            return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
    <title>Vault Approval Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 700px;
            margin: 0 auto;
            padding: 40px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .header {{
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 600;
        }}
        .header p {{
            opacity: 0.9;
            font-size: 1.2em;
        }}
        .card {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }}
        .status-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 25px 0;
        }}
        .status-item {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            border: 2px solid #e9ecef;
        }}
        .status-item .value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            display: block;
            margin: 10px 0;
        }}
        .status-item .label {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        .action-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
            margin: 10px 10px 10px 0;
        }}
        .action-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
        .action-button.secondary {{
            background: #6c757d;
        }}
        .info-box {{
            background: #e7f3ff;
            border-left: 4px solid #0066cc;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .success-box {{
            background: #d4edda;
            border-left: 4px solid #28a745;
        }}
        .warning-box {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
        }}
        h2 {{
            color: #333;
            margin-bottom: 15px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 Vault Approval</h1>
        <p>Secure Secret Management</p>
    </div>

    <div class="card">
        <h2>Server Status</h2>

        <div class="status-grid">
            <div class="status-item">
                <div class="value">✅</div>
                <div class="label">Running</div>
            </div>
            <div class="status-item">
                <div class="value">{len(self.pending_ops)}</div>
                <div class="label">Pending Operations</div>
            </div>
            <div class="status-item">
                <div class="value">{len(self.credentials_db)}</div>
                <div class="label">Registered Devices</div>
            </div>
        </div>

        {'<div class="info-box success-box"><strong>✓ Setup Complete</strong><br>Your authenticator is registered and ready to approve operations.</div>' if has_auth else '<div class="info-box warning-box"><strong>⚠ Setup Required</strong><br>Register your authenticator (TouchID, Windows Hello, or YubiKey) before you can approve Vault operations.</div>'}

        <h2 style="margin-top: 30px;">Actions</h2>

        {'<a href="/register" class="action-button secondary">Manage Authenticators</a>' if has_auth else '<a href="/register" class="action-button">Register Authenticator</a>'}

        <div class="info-box" style="margin-top: 30px;">
            <p><strong>How it works:</strong></p>
            <p>When Claude Code needs to write secrets to Vault, you'll receive an approval URL. Open it in your browser, review the changes, and authenticate with your registered device to approve.</p>
        </div>
    </div>
</body>
</html>
            """)

        @self.app.get("/register")
        async def register_page():
            """WebAuthn registration page."""
            return HTMLResponse(self._get_register_html())

        @self.app.post("/webauthn/register/options")
        async def register_options():
            """Generate WebAuthn registration options."""
            user_id = b"vault-admin"  # Single user for homelab (must be bytes)

            options = generate_registration_options(
                rp_id=self.domain,
                rp_name="Vault Approval",
                user_id=user_id,
                user_name="Vault Admin",
                authenticator_selection=AuthenticatorSelectionCriteria(
                    authenticator_attachment=AuthenticatorAttachment.PLATFORM,
                    user_verification=UserVerificationRequirement.REQUIRED,
                ),
                supported_pub_key_algs=[
                    COSEAlgorithmIdentifier.ECDSA_SHA_256,
                    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
                ],
            )

            # Store challenge
            session_id = secrets.token_urlsafe(32)
            self.challenges[session_id] = options.challenge

            return JSONResponse({
                "options": json.loads(options_to_json(options)),
                "sessionId": session_id
            })

        @self.app.post("/webauthn/register/verify")
        async def register_verify(request: Request):
            """Verify WebAuthn registration response."""
            data = await request.json()
            session_id = data.get("sessionId")
            credential = data.get("credential")

            if not session_id or session_id not in self.challenges:
                raise HTTPException(400, "Invalid session")

            challenge = self.challenges.pop(session_id)

            try:
                verification = verify_registration_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=self.domain,
                    expected_origin=self.origin,
                )

                # Store credential
                user_id = "vault-admin"
                self.credentials_db[user_id] = {
                    "credential_id": verification.credential_id.hex(),
                    "public_key": verification.credential_public_key.hex(),
                    "sign_count": verification.sign_count,
                    "created_at": datetime.now().isoformat(),
                }
                self._save_credentials()

                return {"success": True, "message": "Authenticator registered successfully!"}
            except Exception as e:
                raise HTTPException(400, f"Registration failed: {e}")

        @self.app.get("/approve/{op_id}")
        async def approve_page(op_id: str):
            """WebAuthn approval page for pending operation."""
            if op_id not in self.pending_ops:
                raise HTTPException(404, "Operation not found or expired")

            op = self.pending_ops[op_id]

            # Check expiry (5 minutes)
            if datetime.now().timestamp() - op.created_at > 300:
                del self.pending_ops[op_id]
                raise HTTPException(410, "Operation expired (max 5 minutes)")

            return HTMLResponse(self._get_approval_html(op))

        @self.app.post("/webauthn/authenticate/options")
        async def authenticate_options():
            """Generate WebAuthn authentication options."""
            user_id = "vault-admin"

            if user_id not in self.credentials_db:
                raise HTTPException(400, "No registered authenticator. Please register first.")

            credential = self.credentials_db[user_id]

            options = generate_authentication_options(
                rp_id=self.domain,
                allow_credentials=[PublicKeyCredentialDescriptor(
                    id=bytes.fromhex(credential["credential_id"])
                )],
                user_verification=UserVerificationRequirement.REQUIRED,
            )

            # Store challenge
            session_id = secrets.token_urlsafe(32)
            self.challenges[session_id] = options.challenge

            return JSONResponse({
                "options": json.loads(options_to_json(options)),
                "sessionId": session_id
            })

        @self.app.post("/webauthn/authenticate/verify")
        async def authenticate_verify(request: Request):
            """Verify WebAuthn authentication and approve operation."""
            data = await request.json()
            session_id = data.get("sessionId")
            credential = data.get("credential")
            op_id = data.get("opId")

            if not session_id or session_id not in self.challenges:
                raise HTTPException(400, "Invalid session")

            if op_id not in self.pending_ops:
                raise HTTPException(404, "Operation not found")

            challenge = self.challenges.pop(session_id)
            user_id = "vault-admin"

            if user_id not in self.credentials_db:
                raise HTTPException(400, "No registered authenticator")

            stored_credential = self.credentials_db[user_id]

            try:
                verification = verify_authentication_response(
                    credential=credential,
                    expected_challenge=challenge,
                    expected_rp_id=self.domain,
                    expected_origin=self.origin,
                    credential_public_key=bytes.fromhex(stored_credential["public_key"]),
                    credential_current_sign_count=stored_credential["sign_count"],
                )

                # Update sign count
                stored_credential["sign_count"] = verification.new_sign_count
                self._save_credentials()

                # Approve operation
                op = self.pending_ops[op_id]
                op.approved = True
                op.approved_at = datetime.now().timestamp()

                return {
                    "success": True,
                    "message": f"Operation approved! Vault write to '{op.service}' is now authorized."
                }
            except Exception as e:
                raise HTTPException(400, f"Authentication failed: {e}")

        @self.app.get("/status/{op_id}")
        async def check_status(op_id: str):
            """Check if operation is approved."""
            if op_id not in self.pending_ops:
                return {"approved": False, "error": "Operation not found"}

            op = self.pending_ops[op_id]
            return {"approved": op.approved}

    def _get_register_html(self) -> str:
        """Get HTML for WebAuthn registration page."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Register Authenticator - Vault Approval</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            max-width: 700px;
            margin: 0 auto;
            padding: 40px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 2em;
            margin-bottom: 10px;
            font-weight: 600;
        }
        .header p {
            opacity: 0.9;
            font-size: 1.1em;
        }
        .card {
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .back-link {
            display: inline-block;
            margin-bottom: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            transition: transform 0.2s;
        }
        .back-link:hover {
            transform: translateX(-5px);
        }
        .back-link::before {
            content: "← ";
        }
        h2 {
            color: #333;
            margin-bottom: 20px;
            font-size: 1.5em;
        }
        .info-box {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .info-box p {
            color: #495057;
            line-height: 1.6;
            margin: 5px 0;
        }
        .info-box strong {
            color: #333;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-top: 20px;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        button:active {
            transform: translateY(0);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        #status {
            margin-top: 20px;
            padding: 15px;
            border-radius: 8px;
            display: none;
        }
        #status.show { display: block; }
        .success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .loading {
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        .icon {
            font-size: 2em;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 Vault Approval</h1>
        <p>Secure Secret Management</p>
    </div>

    <div class="card">
        <a href="/" class="back-link">Back to home</a>

        <h2>Register Authenticator</h2>

        <div class="info-box">
            <p><strong>What is this?</strong></p>
            <p>Register your device's biometric authentication (TouchID, Windows Hello, or hardware security key) to securely approve Vault write operations.</p>
        </div>

        <div class="info-box">
            <p><strong>Supported authenticators:</strong></p>
            <p>🍎 TouchID (macOS) • 🪟 Windows Hello • 🔑 YubiKey • 📱 Phone authenticators</p>
        </div>

        <button onclick="register()" id="registerBtn">
            Register Authenticator
        </button>

        <div id="status"></div>
    </div>

    <script>
        function base64ToArrayBuffer(base64) {
            const binary = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {
                bytes[i] = binary.charCodeAt(i);
            }
            return bytes.buffer;
        }

        async function register() {
            const status = document.getElementById('status');
            const btn = document.getElementById('registerBtn');

            btn.disabled = true;
            status.className = 'loading show';
            status.innerHTML = '⏳ Requesting registration options...';

            try {
                // Get registration options
                const optionsRes = await fetch('/webauthn/register/options', { method: 'POST' });
                const { options, sessionId } = await optionsRes.json();

                // Convert base64 strings to ArrayBuffers
                options.user.id = base64ToArrayBuffer(options.user.id);
                options.challenge = base64ToArrayBuffer(options.challenge);

                status.innerHTML = '👆 Touch your authenticator to register...';

                // Create credential
                const credential = await navigator.credentials.create({
                    publicKey: options
                });

                status.innerHTML = '✓ Verifying registration...';

                // Verify registration
                const verifyRes = await fetch('/webauthn/register/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        sessionId,
                        credential: {
                            id: credential.id,
                            rawId: arrayBufferToBase64(credential.rawId),
                            response: {
                                clientDataJSON: arrayBufferToBase64(credential.response.clientDataJSON),
                                attestationObject: arrayBufferToBase64(credential.response.attestationObject),
                            },
                            type: credential.type,
                        }
                    })
                });

                const result = await verifyRes.json();

                if (result.success) {
                    status.className = 'success show';
                    status.innerHTML = '✅ <strong>Success!</strong><br><br>' + result.message + '<br><br>You can now approve Vault operations.<br><a href="/" style="color: #155724; font-weight: 600;">← Return to home</a>';
                } else {
                    throw new Error(result.message || 'Registration failed');
                }
            } catch (err) {
                status.className = 'error show';
                status.innerHTML = '❌ <strong>Error:</strong> ' + err.message + '<br><br>Please try again or check the browser console for details.';
                btn.disabled = false;
            }
        }

        function arrayBufferToBase64(buffer) {
            return btoa(String.fromCharCode(...new Uint8Array(buffer)));
        }
    </script>
</body>
</html>
"""

    def _get_approval_html(self, op: PendingOperation) -> str:
        """Get HTML for approval page."""
        secrets_html = "<ul>" + "".join(f"<li><strong>{k}</strong></li>" for k in op.secrets.keys()) + "</ul>"

        warnings_html = ""
        if op.warnings:
            warnings_html = '<div class="warnings">⚠️ <strong>Security Warnings:</strong><ul>' + \
                          "".join(f"<li>{w}</li>" for w in op.warnings) + '</ul></div>'

        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Approve Vault Operation</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 700px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .card {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #333; margin-top: 0; }}
        .info {{ background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .warnings {{ background: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .secrets {{ background: #f8f9fa; padding: 15px; border-radius: 5px; }}
        button {{
            background: #28a745;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin-right: 10px;
        }}
        button:hover {{ background: #218838; }}
        .deny {{ background: #dc3545; }}
        .deny:hover {{ background: #c82333; }}
        #status {{ margin-top: 20px; padding: 15px; border-radius: 5px; }}
        .success {{ background: #d4edda; color: #155724; }}
        .error {{ background: #f8d7da; color: #721c24; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🔐 Vault Operation Approval</h1>

        <div class="info">
            <p><strong>Service:</strong> {op.service}</p>
            <p><strong>Action:</strong> {op.action}</p>
            <p><strong>Path:</strong> secret/proxmox-services/{op.service}</p>
        </div>

        {warnings_html}

        <div class="secrets">
            <h3>Secrets to be written:</h3>
            {secrets_html}
        </div>

        <p style="margin-top: 20px;">
            <button onclick="approve()">✅ Approve with WebAuthn</button>
            <button class="deny" onclick="deny()">❌ Deny</button>
        </p>

        <div id="status"></div>
    </div>

    <script>
        const opId = '{op.op_id}';

        function base64ToArrayBuffer(base64) {{
            const binary = atob(base64.replace(/-/g, '+').replace(/_/g, '/'));
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) {{
                bytes[i] = binary.charCodeAt(i);
            }}
            return bytes.buffer;
        }}

        async function approve() {{
            const status = document.getElementById('status');
            status.innerHTML = 'Requesting authentication...';

            try {{
                // Get authentication options
                const optionsRes = await fetch('/webauthn/authenticate/options', {{ method: 'POST' }});
                const {{ options, sessionId }} = await optionsRes.json();

                // Convert base64 strings to ArrayBuffers
                options.challenge = base64ToArrayBuffer(options.challenge);
                if (options.allowCredentials) {{
                    options.allowCredentials.forEach(cred => {{
                        cred.id = base64ToArrayBuffer(cred.id);
                    }});
                }}

                status.innerHTML = 'Touch your authenticator to approve...';

                // Get credential
                const credential = await navigator.credentials.get({{
                    publicKey: options
                }});

                status.innerHTML = 'Verifying...';

                // Verify authentication
                const verifyRes = await fetch('/webauthn/authenticate/verify', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        sessionId,
                        opId,
                        credential: {{
                            id: credential.id,
                            rawId: arrayBufferToBase64(credential.rawId),
                            response: {{
                                clientDataJSON: arrayBufferToBase64(credential.response.clientDataJSON),
                                authenticatorData: arrayBufferToBase64(credential.response.authenticatorData),
                                signature: arrayBufferToBase64(credential.response.signature),
                                userHandle: credential.response.userHandle ? arrayBufferToBase64(credential.response.userHandle) : null,
                            }},
                            type: credential.type,
                        }}
                    }})
                }});

                const result = await verifyRes.json();

                if (result.success) {{
                    status.className = 'success';
                    status.innerHTML = '✅ ' + result.message + '<br><br>You can close this window.';
                }} else {{
                    throw new Error(result.message || 'Approval failed');
                }}
            }} catch (err) {{
                status.className = 'error';
                status.innerHTML = '❌ Error: ' + err.message;
            }}
        }}

        function deny() {{
            window.close();
        }}

        function arrayBufferToBase64(buffer) {{
            return btoa(String.fromCharCode(...new Uint8Array(buffer)));
        }}
    </script>
</body>
</html>
"""

    def create_pending_operation(
        self,
        service: str,
        action: str,
        secrets: Dict[str, str],
        warnings: list = None
    ) -> tuple[str, str]:
        """Create a pending operation and return (operation ID, approval URL)."""
        op_id = secrets.token_urlsafe(16)

        self.pending_ops[op_id] = PendingOperation(
            op_id=op_id,
            service=service,
            action=action,
            secrets=secrets,
            warnings=warnings or [],
            created_at=datetime.now().timestamp()
        )

        # Generate approval URL based on configured origin
        approval_url = f"{self.origin}/approve/{op_id}"

        return op_id, approval_url

    def is_approved(self, op_id: str) -> bool:
        """Check if operation is approved."""
        if op_id not in self.pending_ops:
            return False

        op = self.pending_ops[op_id]

        # Check expiry
        if datetime.now().timestamp() - op.created_at > 300:  # 5 minutes
            del self.pending_ops[op_id]
            return False

        return op.approved

    def cleanup_operation(self, op_id: str):
        """Remove operation after it's been executed."""
        if op_id in self.pending_ops:
            del self.pending_ops[op_id]

    def start(self):
        """Start the approval server in a background thread."""
        if self.server_thread and self.server_thread.is_alive():
            return  # Already running

        def run_server():
            uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="warning")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        print(f"✅ Approval server started on http://localhost:{self.port}", file=sys.stderr)


# Global instance
_approval_server: Optional[ApprovalServer] = None


def get_approval_server() -> ApprovalServer:
    """Get or create the global approval server instance."""
    global _approval_server
    if _approval_server is None:
        # Read configuration from environment variables
        domain = os.getenv('VAULT_APPROVE_DOMAIN', 'vault-approve.laboiteaframboises.duckdns.org')
        origin = os.getenv('VAULT_APPROVE_ORIGIN', f'https://{domain}')
        port = int(os.getenv('VAULT_APPROVE_PORT', '8091'))

        _approval_server = ApprovalServer(port=port, domain=domain, origin=origin)
        _approval_server.start()
    return _approval_server


def main():
    """Standalone approval server (for debugging)."""
    import sys
    server = ApprovalServer()
    print(f"🔐 Vault Approval Server")
    print(f"Running on http://localhost:{server.port}")
    print(f"Press Ctrl+C to stop")

    try:
        uvicorn.run(server.app, host="0.0.0.0", port=server.port)
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    main()
