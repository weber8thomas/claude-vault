"""WebAuthn approval server for vault_set operations."""

import json
import os
import secrets as secrets_module
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)


@dataclass
class PendingOperation:
    """Pending vault operation awaiting approval."""

    op_id: str
    service: str
    action: str  # CREATE, UPDATE, SCAN_ENV, SCAN_COMPOSE
    secrets: Dict[str, str]  # Detokenized values for display
    warnings: list
    created_at: float
    approved: bool = False
    approved_at: Optional[float] = None
    scan_file_path: Optional[str] = None  # For scan operations
    metadata: Optional[Dict] = None  # Additional metadata
    tokens_map: Optional[Dict[str, str]] = None  # Maps secret_key -> token (for display)
    approved_by_credential: Optional[str] = None  # credential_id used for approval
    approved_by_device: Optional[str] = None  # device name used for approval


class ApprovalServer:
    """Manages pending operations and WebAuthn approvals."""

    def __init__(
        self,
        port: int = 8091,
        domain: str = "vault-approve.laboiteaframboises.duckdns.org",
        origin: str = "https://vault-approve.laboiteaframboises.duckdns.org",
    ):
        self.port = port
        self.domain = domain  # rp_id for WebAuthn
        self.origin = origin  # Expected origin for WebAuthn
        self.app = FastAPI()
        self.pending_ops: Dict[str, PendingOperation] = {}
        self.completed_ops: Dict[str, PendingOperation] = {}  # History
        self.credentials_db: Dict[str, dict] = {}  # user_id -> credential
        self.challenges: Dict[str, bytes] = {}  # session_id -> challenge

        # Storage paths
        self.storage_dir = Path.home() / ".claude-vault"
        self.storage_dir.mkdir(exist_ok=True)
        self.credentials_file = self.storage_dir / "webauthn-credentials.json"
        self.pending_ops_file = self.storage_dir / "pending-operations.json"
        self.completed_ops_file = self.storage_dir / "completed-operations.json"

        # Load existing credentials and operations
        self._load_credentials()
        self._load_pending_operations()
        self._load_completed_operations()

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

    def _load_pending_operations(self):
        """Load pending operations from disk."""
        if self.pending_ops_file.exists():
            try:
                data = json.loads(self.pending_ops_file.read_text())
                # Convert dict to PendingOperation objects
                for op_id, op_data in data.items():
                    self.pending_ops[op_id] = PendingOperation(**op_data)
                # Clean up expired operations (older than 5 minutes)
                now = datetime.now().timestamp()
                expired = [
                    op_id for op_id, op in self.pending_ops.items() if now - op.created_at > 300
                ]
                for op_id in expired:
                    del self.pending_ops[op_id]
                if expired:
                    self._save_pending_operations()
            except Exception as e:
                print(f"Warning: Could not load pending operations: {e}", file=sys.stderr)

    def _save_pending_operations(self):
        """Save pending operations to disk."""
        try:
            # Convert PendingOperation objects to dicts
            data = {op_id: asdict(op) for op_id, op in self.pending_ops.items()}
            self.pending_ops_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Warning: Could not save pending operations: {e}", file=sys.stderr)

    def _load_completed_operations(self):
        """Load completed operations from disk."""
        if self.completed_ops_file.exists():
            try:
                data = json.loads(self.completed_ops_file.read_text())
                # Convert dict to PendingOperation objects
                for op_id, op_data in data.items():
                    self.completed_ops[op_id] = PendingOperation(**op_data)
                # Keep all completed operations indefinitely (no cleanup)
            except Exception as e:
                print(f"Warning: Could not load completed operations: {e}", file=sys.stderr)

    def _save_completed_operations(self):
        """Save completed operations to disk."""
        try:
            # Convert PendingOperation objects to dicts
            data = {op_id: asdict(op) for op_id, op in self.completed_ops.items()}
            self.completed_ops_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"Warning: Could not save completed operations: {e}", file=sys.stderr)

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/favicon.ico")
        async def favicon():
            """Serve favicon."""
            # SVG favicon with vault/lock icon
            svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
                <rect width="100" height="100" rx="20" fill="#667eea"/>
                <path d="M50 25 L50 35 M35 45 L35 55 Q35 75 50 75 Q65 75 65 55 L65 45 Z"
                      stroke="#fff" stroke-width="8" fill="none" stroke-linecap="round"/>
                <rect x="30" y="45" width="40" height="30" rx="5" fill="#fff"/>
                <circle cx="50" cy="60" r="4" fill="#667eea"/>
                <rect x="48" y="60" width="4" height="8" fill="#667eea"/>
            </svg>"""
            return HTMLResponse(
                content=svg,
                media_type="image/svg+xml",
                headers={
                    "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                    "X-Content-Type-Options": "nosniff",
                },
            )

        @self.app.get("/")
        async def index():
            """Server status page."""
            has_auth = len(self.credentials_db) > 0

            # Generate status box HTML
            if has_auth:
                status_box = (
                    '<div class="info-box success-box">'
                    "<strong>✓ Setup Complete</strong><br>"
                    "Your authenticator is registered and ready to approve "
                    "operations.</div>"
                )
                auth_button = (
                    '<a href="/register" class="action-button secondary">'
                    "⚙️ Manage Authenticators</a>"
                )
                reset_button = (
                    '<button onclick="resetCredentials()" class="action-button" '
                    'style="background: #dc3545;">'
                    "🗑️ Reset Authenticator</button>"
                )
            else:
                status_box = (
                    '<div class="info-box warning-box">'
                    "<strong>⚠ Setup Required</strong><br>"
                    "Register your authenticator (TouchID, Windows Hello, or "
                    "YubiKey) before you can approve Claude-Vault operations."
                    "</div>"
                )
                auth_button = (
                    '<a href="/register" class="action-button">' "⚙️ Register Authenticator</a>"
                )
                reset_button = ""

            return HTMLResponse(
                f"""
<!DOCTYPE html>
<html>
<head>
    <title>Claude-Vault Approval Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 1100px;
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
            border: none;
            cursor: pointer;
            font-size: 16px;
        }}
        .action-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
        .action-button.secondary {{
            background: #6c757d;
        }}
        button.action-button {{
            width: auto;
            display: inline-block;
        }}
        .action-buttons-container {{
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            margin: 10px 0;
        }}
        .action-buttons-container .action-button {{
            margin: 0;
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
        .list-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .list-table th {{
            background: #f8f9fa;
            padding: 14px 16px;
            text-align: left;
            font-weight: 600;
            color: #495057;
            border-bottom: 2px solid #dee2e6;
        }}
        .list-table td {{
            padding: 14px 16px;
            border-bottom: 1px solid #e9ecef;
            color: #495057;
        }}
        .list-table tr:last-child td {{
            border-bottom: none;
        }}
        .list-table th:first-child,
        .list-table td:first-child {{
            width: 25%;
        }}
        .clickable-row {{
            cursor: pointer;
            transition: background-color 0.2s ease;
        }}
        .clickable-row:hover {{
            background-color: #f0f4ff;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .badge-success {{
            background: #d4edda;
            color: #155724;
        }}
        .badge-warning {{
            background: #fff3cd;
            color: #856404;
        }}
        .badge-info {{
            background: #d1ecf1;
            color: #0c5460;
        }}
        .badge-secondary {{
            background: #e2e3e5;
            color: #383d41;
        }}
        .empty-state {{
            text-align: center;
            padding: 30px;
            color: #6c757d;
            font-style: italic;
        }}
        .credential-id {{
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 0.85em;
            color: #6c757d;
        }}
        .time-ago {{
            font-size: 0.9em;
            color: #6c757d;
        }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
            animation: fadeIn 0.3s;
        }}
        .modal-content {{
            background-color: white;
            margin: 5% auto;
            padding: 0;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            width: 90%;
            max-width: 900px;
            max-height: 80vh;
            overflow-y: auto;
            animation: slideDown 0.3s;
        }}
        .modal-header {{
            background: linear-gradient(135deg, rgb(102,126,234) 0%, rgb(118,75,162) 100%);
            color: white;
            padding: 20px 30px;
            border-radius: 15px 15px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .modal-header h2 {{
            margin: 0;
            font-size: 1.5em;
        }}
        .modal-close {{
            color: white;
            font-size: 35px;
            font-weight: bold;
            cursor: pointer;
            line-height: 1;
        }}
        .modal-close:hover {{
            color: #f0f0f0;
        }}
        .modal-body {{
            padding: 30px;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        @keyframes slideDown {{
            from {{ transform: translateY(-50px); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}
        .detail-section {{
            margin-bottom: 25px;
        }}
        .detail-section h3 {{
            color: #495057;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }}
        .detail-grid {{
            display: grid;
            grid-template-columns: 200px 1fr;
            gap: 12px;
            margin-top: 10px;
        }}
        .detail-label {{
            font-weight: 600;
            color: #6c757d;
        }}
        .detail-value {{
            color: #495057;
        }}
        .detail-value code {{
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 0.9em;
        }}
        @media (max-width: 1200px) {{
            body {{
                padding: 20px 10px;
            }}
            .card {{
                padding: 30px 20px;
            }}
            .modal-content {{
                width: 95%;
                margin: 2% auto;
            }}
            .detail-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 Claude-Vault Approval</h1>
        <p>AI-Assisted Secret Management</p>
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

        {status_box}

        <h2 style="margin-top: 30px;">Actions</h2>

        <div class="action-buttons-container">
            {auth_button}
            {reset_button}
        </div>

        <div class="info-box" style="margin-top: 30px;">
            <p><strong>How it works:</strong></p>
            <p>When Claude Code needs to write secrets to Claude-Vault, you'll receive an
            approval URL. Open it in your browser, review the changes, and authenticate
            with your registered device to approve.</p>
        </div>
    </div>

    {self._get_registered_devices_html()}
    {self._get_pending_operations_html()}
    {self._get_history_html()}

    <script>
        async function resetCredentials() {{
            if (!confirm(
                '⚠️ Are you sure you want to delete all registered authenticators?\\n\\n'
                + 'You will need to re-register your device to approve vault operations.'
            )) {{
                return;
            }}

            try {{
                const response = await fetch('/reset-credentials', {{ method: 'POST' }});
                const result = await response.json();

                if (result.success) {{
                    alert('✅ ' + result.message);
                    window.location.reload();
                }} else {{
                    alert('❌ Failed to reset credentials: ' + (result.message || 'Unknown error'));
                }}
            }} catch (err) {{
                alert('❌ Error: ' + err.message);
            }}
        }}

        // Store operation details globally (populated from server)
        // Note: operationDetails is populated by the history section if present
        if (typeof operationDetails === 'undefined') {{
            var operationDetails = {{}};
        }}

        function showOperationDetails(opId) {{
            const op = operationDetails[opId];
            if (!op) {{
                alert('Operation details not found');
                return;
            }}

            // Build modal content
            const modalBody = document.getElementById('modalBody');
            const modalTitle = document.getElementById('modalTitle');

            modalTitle.textContent = `Operation: ${{op.service}}`;

            // Build HTML for operation details
            let html = `
                <div class="detail-section">
                    <h3>📋 Operation Information</h3>
                    <div class="detail-grid">
                        <div class="detail-label">Service:</div>
                        <div class="detail-value"><strong>${{op.service}}</strong></div>

                        <div class="detail-label">Action:</div>
                        <div class="detail-value">
                            <span class="badge badge-info">${{op.action}}</span>
                        </div>

                        <div class="detail-label">Operation ID:</div>
                        <div class="detail-value"><code>${{op.op_id}}</code></div>

                        <div class="detail-label">Status:</div>
                        <div class="detail-value">
                            <span class="badge badge-success">Completed</span>
                        </div>
                    </div>
                </div>

                <div class="detail-section">
                    <h3>⏰ Timeline</h3>
                    <div class="detail-grid">
                        <div class="detail-label">Created:</div>
                        <div class="detail-value">
                            ${{formatTimestamp(op.created_at)}}
                        </div>

                        <div class="detail-label">Approved:</div>
                        <div class="detail-value">
                            ${{op.approved_at ? formatTimestamp(op.approved_at) : 'N/A'}}
                        </div>

                        <div class="detail-label">Duration:</div>
                        <div class="detail-value">
                            ${{calculateDuration(op.created_at, op.approved_at)}}
                        </div>
                    </div>
                </div>

                <div class="detail-section">
                    <h3>🔐 Secrets (${{Object.keys(op.secrets).length}})</h3>
                    <table class="list-table">
                        <thead>
                            <tr>
                                <th style="width: 30%">Key</th>
                                <th style="width: 70%">Value</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            // Add secrets rows
            for (const [key, value] of Object.entries(op.secrets)) {{
                html += `
                    <tr>
                        <td><strong>${{escapeHtml(key)}}</strong></td>
                        <td><code>${{escapeHtml(value)}}</code></td>
                    </tr>
                `;
            }}

            html += `
                        </tbody>
                    </table>
                </div>

                <div class="detail-section">
                    <h3>👤 Approval Details</h3>
                    <div class="detail-grid">
                        <div class="detail-label">Device Used:</div>
                        <div class="detail-value">
                            ${{op.approved_by_device || 'N/A'}}
                        </div>

                        <div class="detail-label">Credential ID:</div>
                        <div class="detail-value">
                            <code>
                                ${{op.approved_by_credential
                                    ? op.approved_by_credential.substring(0, 20) + '...'
                                    : 'N/A'}}
                            </code>
                        </div>
                    </div>
                </div>
            `;

            // Add scan information if present
            if (op.scan_file_path) {{
                html += `
                <div class="detail-section">
                    <h3>📄 Scan Information</h3>
                    <div class="detail-grid">
                        <div class="detail-label">Source File:</div>
                        <div class="detail-value">
                            <code>${{escapeHtml(op.scan_file_path)}}</code>
                        </div>

                        <div class="detail-label">Secrets Found:</div>
                        <div class="detail-value">
                            ${{op.metadata?.secret_count || Object.keys(op.secrets).length}}
                        </div>

                        <div class="detail-label">Config Values:</div>
                        <div class="detail-value">
                            ${{op.metadata?.config_count || 'N/A'}}
                        </div>
                    </div>
                </div>
                `;
            }}

            modalBody.innerHTML = html;

            // Show modal
            document.getElementById('operationModal').style.display = 'block';
        }}

        function closeModal() {{
            document.getElementById('operationModal').style.display = 'none';
        }}

        // Close modal when clicking outside
        window.onclick = function(event) {{
            const modal = document.getElementById('operationModal');
            if (event.target == modal) {{
                closeModal();
            }}
        }}

        // Utility functions
        function formatTimestamp(timestamp) {{
            if (!timestamp) return 'N/A';
            const date = new Date(timestamp * 1000);
            return date.toLocaleString('en-US', {{
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            }});
        }}

        function calculateDuration(start, end) {{
            if (!start || !end) return 'N/A';
            const duration = end - start;
            if (duration < 60) return `${{Math.round(duration)}}s`;
            if (duration < 3600) return `${{Math.round(duration / 60)}}m`;
            return `${{Math.round(duration / 3600)}}h`;
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }}
    </script>

    <!-- Operation Details Modal -->
    <div id="operationModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modalTitle">Operation Details</h2>
                <span class="modal-close" onclick="closeModal()">&times;</span>
            </div>
            <div class="modal-body" id="modalBody">
                <!-- Details populated by JavaScript -->
            </div>
        </div>
    </div>
</body>
</html>
            """
            )

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
                rp_name="Claude-Vault Approval",
                user_id=user_id,
                user_name="Claude-Vault Admin",
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
            session_id = secrets_module.token_urlsafe(32)
            self.challenges[session_id] = options.challenge

            return JSONResponse(
                {"options": json.loads(options_to_json(options)), "sessionId": session_id}
            )

        @self.app.post("/webauthn/register/verify")
        async def register_verify(request: Request):
            """Verify WebAuthn registration response."""
            data = await request.json()
            session_id = data.get("sessionId")
            credential = data.get("credential")
            device_name = data.get("deviceName", "Unnamed Device")

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
                now_timestamp = datetime.now().timestamp()
                self.credentials_db[user_id] = {
                    "credential_id": verification.credential_id.hex(),
                    "public_key": verification.credential_public_key.hex(),
                    "sign_count": verification.sign_count,
                    "created_at": datetime.now().isoformat(),
                    "registered_at": now_timestamp,
                    "device_name": device_name,
                }
                self._save_credentials()

                return {"success": True, "message": "Authenticator registered successfully!"}
            except Exception as e:
                raise HTTPException(400, f"Registration failed: {e}")

        @self.app.get("/approve/{op_id}")
        async def approve_page(op_id: str):
            """WebAuthn approval page for pending operation."""
            # Reload from disk to get operations created by other processes
            self._load_pending_operations()

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
                allow_credentials=[
                    PublicKeyCredentialDescriptor(id=bytes.fromhex(credential["credential_id"]))
                ],
                user_verification=UserVerificationRequirement.REQUIRED,
            )

            # Store challenge
            session_id = secrets_module.token_urlsafe(32)
            self.challenges[session_id] = options.challenge

            return JSONResponse(
                {"options": json.loads(options_to_json(options)), "sessionId": session_id}
            )

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
                op.approved_by_credential = verification.credential_id.hex()
                op.approved_by_device = stored_credential.get("device_name", "Unknown Device")

                # Save to disk for cross-process sharing
                self._save_pending_operations()

                return {
                    "success": True,
                    "message": (
                        "Operation approved! Claude-Vault write to '{}' " "is now authorized."
                    ).format(op.service),
                }
            except Exception as e:
                raise HTTPException(400, f"Authentication failed: {e}")

        @self.app.get("/status/{op_id}")
        async def check_status(op_id: str):
            """Check if operation is approved."""
            # Reload from disk to get operations created by other processes
            self._load_pending_operations()

            if op_id not in self.pending_ops:
                return {"approved": False, "error": "Operation not found"}

            op = self.pending_ops[op_id]
            return {"approved": op.approved}

        @self.app.post("/reset-credentials")
        async def reset_credentials():
            """Delete all registered authenticators."""
            try:
                self.credentials_db = {}
                self._save_credentials()
                return {
                    "success": True,
                    "message": (
                        "All authenticators have been deleted. "
                        "You can now register a new device."
                    ),
                }
            except Exception as e:
                raise HTTPException(500, "Failed to reset credentials: {}".format(e))

    def _get_registered_devices_html(self) -> str:
        """Generate HTML for registered devices section."""
        if not self.credentials_db:
            return """
    <div class="card">
        <h2>🔑 Registered Devices</h2>
        <div class="empty-state">No devices registered yet</div>
    </div>
            """

        devices_rows = ""
        for user_id, cred in self.credentials_db.items():
            device_name = cred.get("device_name", "Unnamed Device")
            cred_id_short = cred["credential_id"][:16] + "..."

            # Handle both timestamp and missing registered_at
            registered_at = cred.get("registered_at")
            if registered_at:
                registered_str = datetime.fromtimestamp(registered_at).strftime("%Y-%m-%d %H:%M")
            else:
                # Fallback to created_at if it exists
                created_at = cred.get("created_at")
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at)
                        registered_str = dt.strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError):
                        registered_str = "Unknown"
                else:
                    registered_str = "Unknown"

            devices_rows += f"""
            <tr>
                <td><strong>{device_name}</strong></td>
                <td class="credential-id">{cred_id_short}</td>
                <td><span class="badge badge-success">Active</span></td>
                <td class="time-ago">{registered_str}</td>
            </tr>
            """

        return f"""
    <div class="card">
        <h2>🔑 Registered Devices</h2>
        <table class="list-table">
            <thead>
                <tr>
                    <th>Device Name</th>
                    <th>Credential ID</th>
                    <th>Status</th>
                    <th>Registered</th>
                </tr>
            </thead>
            <tbody>
                {devices_rows}
            </tbody>
        </table>
    </div>
        """

    def _get_pending_operations_html(self) -> str:
        """Generate HTML for pending operations section."""
        # Reload to get latest state
        self._load_pending_operations()

        if not self.pending_ops:
            return """
    <div class="card">
        <h2>📋 Pending Operations</h2>
        <div class="empty-state">No pending operations</div>
    </div>
            """

        ops_rows = ""
        now = datetime.now().timestamp()
        for op_id, op in sorted(
            self.pending_ops.items(), key=lambda x: x[1].created_at, reverse=True
        ):
            age_seconds = int(now - op.created_at)
            if age_seconds < 60:
                age_str = "{}s ago".format(age_seconds)
            elif age_seconds < 3600:
                age_str = "{}m ago".format(age_seconds // 60)
            else:
                age_str = "{}h ago".format(age_seconds // 3600)

            # Format timestamp
            created_time = datetime.fromtimestamp(op.created_at).strftime("%Y-%m-%d %H:%M")

            status_badge = (
                '<span class="badge badge-success">Approved</span>'
                if op.approved
                else '<span class="badge badge-warning">Pending</span>'
            )
            action_badge_class = "badge-info" if op.action == "CREATE" else "badge-secondary"

            ops_rows += """
            <tr>
                <td><strong>{}</strong></td>
                <td><span class="badge {}">{}</span></td>
                <td>{} secret(s)</td>
                <td>{}</td>
                <td class="time-ago">{}</td>
                <td class="time-ago">{}</td>
                <td><a href="/approve/{}" style="color: #667eea; text-decoration: none; '
                'font-weight: 600;">View →</a></td>
            </tr>
            """.format(
                op.service,
                action_badge_class,
                op.action,
                len(op.secrets),
                status_badge,
                created_time,
                age_str,
                op_id,
            )

        return f"""
    <div class="card">
        <h2>📋 Pending Operations</h2>
        <table class="list-table">
            <thead>
                <tr>
                    <th>Service</th>
                    <th>Action</th>
                    <th>Secrets</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Age</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {ops_rows}
            </tbody>
        </table>
    </div>
        """

    def _get_history_html(self) -> str:
        """Generate HTML for completed operations history."""
        # Reload to get latest state
        self._load_completed_operations()

        if not self.completed_ops:
            return """
    <div class="card">
        <h2>📜 Operation History</h2>
        <div class="empty-state">No completed operations yet</div>
    </div>
            """

        # Sort by completion time (most recent first)
        sorted_ops = sorted(
            self.completed_ops.items(),
            key=lambda x: x[1].approved_at or x[1].created_at,
            reverse=True,
        )

        # Limit to last 100 operations
        ops_rows = ""
        now = datetime.now().timestamp()
        for op_id, op in sorted_ops[:100]:
            # Calculate time ago from approved_at or created_at
            ref_time = op.approved_at if op.approved_at else op.created_at
            age_seconds = int(now - ref_time)
            if age_seconds < 60:
                age_str = "{}s ago".format(age_seconds)
            elif age_seconds < 3600:
                age_str = "{}m ago".format(age_seconds // 60)
            else:
                age_str = "{}h ago".format(age_seconds // 3600)

            # Format timestamp
            completed_time = datetime.fromtimestamp(ref_time).strftime("%Y-%m-%d %H:%M")

            action_badge_class = "badge-info" if op.action == "CREATE" else "badge-secondary"

            ops_rows += """
            <tr class="clickable-row" data-op-id="{}" onclick="showOperationDetails('{}')">
                <td><strong>{}</strong></td>
                <td><span class="badge {}">{}</span></td>
                <td>{} secret(s)</td>
                <td><span class="badge badge-success">Completed</span></td>
                <td class="time-ago">{}</td>
                <td class="time-ago">{}</td>
            </tr>
            """.format(
                op_id,
                op_id,
                op.service,
                action_badge_class,
                op.action,
                len(op.secrets),
                completed_time,
                age_str,
            )

        # Build JavaScript data for modal
        import json

        js_data = (
            "    <script>\n"
            "        if (typeof operationDetails === 'undefined') {{\n"
            "            var operationDetails = {{}};\n"
            "        }}\n"
            "        // Add completed operations to modal data\n"
        )
        for op_id, op in sorted_ops[:100]:
            # Serialize operation data as JSON
            op_data = {
                "op_id": op_id,
                "service": op.service,
                "action": op.action,
                "secrets": op.secrets,
                "created_at": op.created_at,
                "approved_at": op.approved_at,
                "scan_file_path": op.scan_file_path,
                "metadata": op.metadata or {},
                "approved_by_credential": getattr(op, "approved_by_credential", None),
                "approved_by_device": getattr(op, "approved_by_device", None),
            }
            js_data += f"        operationDetails['{op_id}'] = {json.dumps(op_data)};\n"
        js_data += "    </script>\n"

        return f"""
    <div class="card">
        <h2>📜 Operation History</h2>
        <p style="color: #6c757d; margin-bottom: 15px;">
        Last 100 completed operations</p>
        <table class="list-table">
            <thead>
                <tr>
                    <th>Service</th>
                    <th>Action</th>
                    <th>Secrets</th>
                    <th>Status</th>
                    <th>Completed</th>
                    <th>Age</th>
                </tr>
            </thead>
            <tbody>
                {ops_rows}
            </tbody>
        </table>
    </div>
    {js_data}
        """

    def _get_register_html(self) -> str:
        """Get HTML for WebAuthn registration page."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Register Authenticator - Claude-Vault Approval</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, sans-serif;
            max-width: 1000px;
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
        .form-group {
            margin: 20px 0;
        }
        .form-group label {
            display: block;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.2s;
        }
        .form-group input:focus {
            outline: none;
            border-color: #667eea;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 Claude-Vault Approval</h1>
        <p>AI-Assisted Secret Management</p>
    </div>

    <div class="card">
        <a href="/" class="back-link">Back to home</a>

        <h2>Register Authenticator</h2>

        <div class="info-box">
            <p><strong>What is this?</strong></p>
            <p>Register your device's biometric authentication (TouchID, Windows Hello,
            or hardware security key) to securely approve Claude-Vault write operations.</p>
        </div>

        <div class="info-box">
            <p><strong>Supported authenticators:</strong></p>
            <p>🍎 TouchID (macOS) • 🪟 Windows Hello • 🔑 YubiKey •
            📱 Phone authenticators</p>
        </div>

        <div class="form-group">
            <label for="deviceName">Device Name</label>
            <input type="text" id="deviceName"
                   placeholder="e.g., My MacBook Pro, Work Laptop, YubiKey"
                   value="">
        </div>

        <button onclick="register()" id="registerBtn">
            Register Authenticator
        </button>

        <div id="status"></div>
    </div>

    <script>
        // Auto-suggest device name based on user agent
        window.addEventListener('DOMContentLoaded', () => {
            const ua = navigator.userAgent;
            let suggestedName = '';

            if (ua.includes('Mac')) {
                suggestedName = 'MacBook';
            } else if (ua.includes('Windows')) {
                suggestedName = 'Windows PC';
            } else if (ua.includes('Linux')) {
                suggestedName = 'Linux Machine';
            } else if (ua.includes('iPhone')) {
                suggestedName = 'iPhone';
            } else if (ua.includes('iPad')) {
                suggestedName = 'iPad';
            } else if (ua.includes('Android')) {
                suggestedName = 'Android Device';
            } else {
                suggestedName = 'My Device';
            }

            document.getElementById('deviceName').value = suggestedName;
        });

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
            const deviceNameInput = document.getElementById('deviceName');
            const deviceName = deviceNameInput.value.trim();

            if (!deviceName) {
                alert('Please enter a device name');
                return;
            }

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
                        deviceName,
                        credential: {
                            id: credential.id,
                            rawId: arrayBufferToBase64(credential.rawId),
                            response: {
                                clientDataJSON: arrayBufferToBase64(
                                    credential.response.clientDataJSON
                                ),
                                attestationObject: arrayBufferToBase64(
                                    credential.response.attestationObject
                                ),
                            },
                            type: credential.type,
                        }
                    })
                });

                const result = await verifyRes.json();

                if (result.success) {
                    status.className = 'success show';
                    status.innerHTML = (
                        '✅ <strong>Success!</strong><br><br>' + result.message +
                        '<br><br>You can now approve Vault operations.<br>'
                        + '<a href="/" style="color: #155724; font-weight: 600;">'
                        + '← Return to home</a>'
                    );
                } else {
                    throw new Error(result.message || 'Registration failed');
                }
            } catch (err) {
                status.className = 'error show';
                status.innerHTML = (
                    '❌ <strong>Error:</strong> ' + err.message + '<br><br>'
                    + 'Please try again or check the browser console for details.'
                );
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

    def _get_scan_approval_html(self, op: PendingOperation) -> str:
        """Get HTML for scan operation approval page."""
        metadata = op.metadata or {}
        secret_count = metadata.get("secret_count", 0)
        config_count = metadata.get("config_count", 0)

        return f"""
<div class="info-box">
    <p><strong>Service:</strong> {op.service}</p>
    <p><strong>File:</strong> {op.scan_file_path}</p>
    <p><strong>Operation:</strong> {op.action}</p>
</div>

<div class="warning-box">
    <h3>⚠️ What This Does</h3>
    <p>This operation will read the file and tokenize detected secrets.</p>
    <p>Secret values will <strong>NOT</strong> be sent to AI - only tokens.</p>
    <p><strong>No files will be modified</strong> during this scan.</p>
    <p style="margin-top: 15px;">Detected:
    <strong>{secret_count} potential secret(s)</strong> and
    <strong>{config_count} config value(s)</strong></p>
</div>
"""

    def _get_approval_html(self, op: PendingOperation) -> str:
        """Get HTML for approval page."""
        # Route to appropriate HTML generator based on action type
        if op.action in ["SCAN_ENV", "SCAN_COMPOSE"]:
            action_specific_html = self._get_scan_approval_html(op)
        else:
            # Default: vault_set operations (CREATE/UPDATE)
            # Generate secrets list with smart truncation for readability
            secrets_rows = ""
            for key, value in op.secrets.items():
                # Smart truncation: show beginning and end for context
                if len(value) <= 40:
                    preview = value  # Show full value if reasonably short
                elif len(value) <= 80:
                    # Medium length: show first 30 + last 10
                    preview = f"{value[:30]}...{value[-10:]}"
                else:
                    # Very long: show first 40 + last 15
                    preview = "{}...{}".format(value[:40], value[-15:])

                # Check if we have a token for this key
                token_display = ""
                if op.tokens_map and key in op.tokens_map:
                    token = op.tokens_map[key]
                    token_display = (
                        '<br><span style="color: #6c757d; ' 'font-size: 0.85em;">Token: {}</span>'
                    ).format(token)

                secrets_rows += f"""
            <tr>
                <td class="secret-key">{key}</td>
                <td class="secret-value"><code>{preview}</code>{token_display}</td>
            </tr>
            """

            # Generate warnings HTML
            warnings_html = ""
            if op.warnings:
                warning_items = "".join(f"<li>{w}</li>" for w in op.warnings)
                warnings_html = f"""
            <div class="warning-box">
                <h3>⚠️ Security Warnings</h3>
                <ul>{warning_items}</ul>
                <p><strong>Review carefully before approving!</strong></p>
            </div>
            """

            action_specific_html = f"""
<div class="info-box">
    <p><strong>Service:</strong> {op.service}</p>
    <p><strong>Action:</strong> <span class="badge badge-{op.action.lower()}">{op.action}</span></p>
    <p><strong>Vault Path:</strong> secret/proxmox-services/{op.service}</p>
</div>

{warnings_html}

<div class="secrets-box">
    <h3>📝 Secrets to Write</h3>
    <table class="secrets-table">
        {secrets_rows}
    </table>
</div>
"""

        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Approve Claude-Vault Operation - {op.service}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/svg+xml" href="/favicon.ico">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                Roboto, "Helvetica Neue", Arial, sans-serif;
            max-width: 1100px;
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
            font-size: 2em;
            margin-bottom: 10px;
            font-weight: 600;
        }}
        .header p {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        .card {{
            background: white;
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            margin-bottom: 20px;
        }}
        .back-link {{
            display: inline-block;
            margin-bottom: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            transition: transform 0.2s;
        }}
        .back-link:hover {{
            transform: translateX(-5px);
        }}
        .back-link::before {{
            content: "← ";
        }}
        h2 {{
            color: #333;
            margin-bottom: 25px;
            font-size: 1.8em;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.7em;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-create {{
            background: #d4edda;
            color: #155724;
        }}
        .badge-update {{
            background: #fff3cd;
            color: #856404;
        }}
        .info-box {{
            background: #e7f3ff;
            border-left: 4px solid #0066cc;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .info-box p {{
            color: #495057;
            line-height: 1.8;
            margin: 8px 0;
        }}
        .info-box strong {{
            color: #333;
            font-weight: 600;
        }}
        .warning-box {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 20px;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .warning-box h3 {{
            color: #856404;
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        .warning-box ul {{
            margin: 10px 0 10px 20px;
            color: #856404;
        }}
        .warning-box li {{
            margin: 5px 0;
        }}
        .warning-box p {{
            color: #856404;
            margin: 8px 0;
        }}
        .secrets-box {{
            background: #f8f9fa;
            border: 2px solid #dee2e6;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .secrets-box h3 {{
            color: #495057;
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        .secrets-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        .secrets-table tr {{
            border-bottom: 1px solid #dee2e6;
        }}
        .secrets-table tr:last-child {{
            border-bottom: none;
        }}
        .secrets-table td {{
            padding: 12px 8px;
        }}
        .secrets-table th {{
            padding: 12px 8px;
            font-weight: 600;
            color: #495057;
        }}
        .secret-key {{
            font-weight: 600;
            color: #495057;
            width: 30%;
        }}
        .secret-value {{
            color: #6c757d;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 0.9em;
            width: 70%;
            word-break: break-all;
        }}
        .secret-value code {{
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 4px;
            color: #495057;
        }}
        .button-group {{
            display: flex;
            gap: 15px;
            margin-top: 30px;
        }}
        button {{
            flex: 1;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        button:hover {{
            transform: translateY(-2px);
        }}
        button:active {{
            transform: translateY(0);
        }}
        button:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }}
        .btn-approve {{
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }}
        .btn-approve:hover {{
            box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4);
        }}
        .btn-deny {{
            background: #6c757d;
            color: white;
        }}
        .btn-deny:hover {{
            background: #5a6268;
        }}
        #status {{
            margin-top: 20px;
            padding: 20px;
            border-radius: 8px;
            display: none;
            text-align: center;
        }}
        #status.show {{ display: block; }}
        .success {{
            background: #d4edda;
            color: #155724;
            border: 2px solid #c3e6cb;
        }}
        .error {{
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #f5c6cb;
        }}
        .loading {{
            background: #fff3cd;
            color: #856404;
            border: 2px solid #ffeaa7;
        }}
        .status-icon {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 Claude-Vault Approval</h1>
        <p>AI-Assisted Secret Management</p>
    </div>

    <div class="card">
        <a href="/" class="back-link">Back to home</a>

        <h2>
            Claude-Vault Operation Approval
            <span class="badge badge-{op.action.lower()}">{op.action}</span>
        </h2>

        {action_specific_html}

        <div class="button-group">
            <button class="btn-approve" onclick="approve()" id="approveBtn">
                ✅ Approve with WebAuthn
            </button>
            <button class="btn-deny" onclick="deny()">
                ❌ Deny & Close
            </button>
        </div>

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
            const approveBtn = document.getElementById('approveBtn');
            const denyBtn = document.querySelector('.btn-deny');

            // Disable buttons during processing
            approveBtn.disabled = true;
            denyBtn.disabled = true;

            // Show loading status
            status.className = 'show loading';
            status.innerHTML = `
                <div class="status-icon">🔄</div>
                <strong>Requesting authentication...</strong>
            `;

            try {{
                // Get authentication options
                const optionsRes = await fetch(
                    '/webauthn/authenticate/options',
                    {{ method: 'POST' }}
                );
                const {{ options, sessionId }} = await optionsRes.json();

                // Convert base64 strings to ArrayBuffers
                options.challenge = base64ToArrayBuffer(options.challenge);
                if (options.allowCredentials) {{
                    options.allowCredentials.forEach(cred => {{
                        cred.id = base64ToArrayBuffer(cred.id);
                    }});
                }}

                // Update status for authenticator prompt
                status.innerHTML = `
                    <div class="status-icon">👆</div>
                    <strong>Touch your authenticator to approve...</strong>
                    <p style="margin-top: 10px;">Use TouchID, Windows Hello,
                    or your security key</p>
                `;

                // Get credential
                const credential = await navigator.credentials.get({{
                    publicKey: options
                }});

                // Update status for verification
                status.innerHTML = `
                    <div class="status-icon">⏳</div>
                    <strong>Verifying authentication...</strong>
                `;

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
                                clientDataJSON: arrayBufferToBase64(
                                    credential.response.clientDataJSON
                                ),
                                authenticatorData: arrayBufferToBase64(
                                    credential.response.authenticatorData
                                ),
                                signature: arrayBufferToBase64(
                                    credential.response.signature
                                ),
                                userHandle: credential.response.userHandle
                                    ? arrayBufferToBase64(credential.response.userHandle)
                                    : null,
                            }},
                            type: credential.type,
                        }}
                    }})
                }});

                const result = await verifyRes.json();

                if (result.success) {{
                    status.className = 'show success';
                    status.innerHTML = `
                        <div class="status-icon">✅</div>
                        <strong>${{result.message}}</strong>
                        <p style="margin-top: 15px;">
                            The secrets have been approved and written to
                            Claude-Vault.
                        </p>
                        <p style="margin-top: 10px; font-size: 0.9em; color: #6c757d;">
                            Operation ID: <code style="background: #e9ecef;
                                                       padding: 2px 6px;
                                                       border-radius: 3px;">${{opId}}</code>
                        </p>
                        <p style="margin-top: 15px; font-size: 0.95em;">
                            Redirecting to home in <span id="countdown">3</span> seconds...
                        </p>
                        <p style="margin-top: 10px;">
                            <a href="/"
                               style="color: #155724; font-weight: 600;
                                      text-decoration: underline;">
                                ← Return to home now
                            </a>
                        </p>
                    `;

                    // Automatic redirect after 3 seconds
                    let countdown = 3;
                    const countdownEl = document.getElementById('countdown');
                    const redirectTimer = setInterval(() => {{
                        countdown--;
                        if (countdownEl) countdownEl.textContent = countdown;
                        if (countdown <= 0) {{
                            clearInterval(redirectTimer);
                            window.location.href = '/';
                        }}
                    }}, 1000);
                }} else {{
                    throw new Error(result.message || 'Approval failed');
                }}
            }} catch (err) {{
                status.className = 'show error';
                status.innerHTML = `
                    <div class="status-icon">❌</div>
                    <strong>Approval Failed</strong>
                    <p style="margin-top: 10px;">${{err.message}}</p>
                `;

                // Re-enable buttons on error so user can retry
                approveBtn.disabled = false;
                denyBtn.disabled = false;
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
        warnings: list = None,
        tokens_map: Dict[str, str] = None,
    ) -> tuple[str, str]:
        """Create a pending operation and return (operation ID, approval URL)."""
        op_id = secrets_module.token_urlsafe(16)

        self.pending_ops[op_id] = PendingOperation(
            op_id=op_id,
            service=service,
            action=action,
            secrets=secrets,
            warnings=warnings or [],
            created_at=datetime.now().timestamp(),
            tokens_map=tokens_map,  # Store token mapping for display
        )

        # Save to disk for cross-process sharing
        self._save_pending_operations()

        # Generate approval URL based on configured origin
        approval_url = f"{self.origin}/approve/{op_id}"

        return op_id, approval_url

    def create_operation(
        self,
        service: str,
        action: str,
        secrets: Dict[str, str],
        warnings: list = None,
        scan_file_path: str = None,
        metadata: Dict = None,
        tokens_map: Dict[str, str] = None,
    ) -> str:
        """
        Create a pending operation and return operation ID.

        This is an extended version that supports scan operations.

        Args:
            service: Service name
            action: Operation action (CREATE, UPDATE, SCAN_ENV, SCAN_COMPOSE)
            secrets: Secret values (may contain tokens like @token-xxx)
            warnings: Security warnings
            scan_file_path: File path for scan operations
            metadata: Additional metadata
            tokens_map: Optional mapping of key names to token values for display

        Returns:
            Operation ID
        """
        op_id = secrets_module.token_urlsafe(16)

        # Secrets are expected to already be detokenized by the calling tool
        # The tokens_map (if provided) maps keys to their original token values for display
        self.pending_ops[op_id] = PendingOperation(
            op_id=op_id,
            service=service,
            action=action,
            secrets=secrets,
            warnings=warnings or [],
            created_at=datetime.now().timestamp(),
            scan_file_path=scan_file_path,
            metadata=metadata,
            tokens_map=tokens_map,
        )

        # Save to disk for cross-process sharing
        self._save_pending_operations()

        return op_id

    def get_approval_url(self, op_id: str) -> str:
        """Get approval URL for an operation."""
        return f"{self.origin}/approve/{op_id}"

    def check_approval(self, op_id: str) -> bool:
        """
        Check if operation is approved.

        This is an alias for is_approved() for consistency with tool interface.
        """
        return self.is_approved(op_id)

    def is_approved(self, op_id: str) -> bool:
        """Check if operation is approved."""
        # Reload from disk to get latest state from other processes
        self._load_pending_operations()

        if op_id not in self.pending_ops:
            return False

        op = self.pending_ops[op_id]

        # Check expiry
        if datetime.now().timestamp() - op.created_at > 300:  # 5 minutes
            del self.pending_ops[op_id]
            return False

        return op.approved

    def cleanup_operation(self, op_id: str):
        """Move operation to history after it's been executed."""
        if op_id in self.pending_ops:
            # Move to completed operations history
            self.completed_ops[op_id] = self.pending_ops[op_id]
            del self.pending_ops[op_id]

            # Save both to disk
            self._save_pending_operations()
            self._save_completed_operations()

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
        domain = os.getenv("VAULT_APPROVE_DOMAIN", "vault-approve.laboiteaframboises.duckdns.org")
        origin = os.getenv("VAULT_APPROVE_ORIGIN", f"https://{domain}")
        port = int(os.getenv("VAULT_APPROVE_PORT", "8091"))

        _approval_server = ApprovalServer(port=port, domain=domain, origin=origin)
        _approval_server.start()
    return _approval_server


def main():
    """Standalone approval server (for debugging)."""
    server = ApprovalServer()
    print("🔐 Claude-Vault Approval Server")
    print(f"Running on http://localhost:{server.port}")
    print("Press Ctrl+C to stop")

    try:
        uvicorn.run(server.app, host="0.0.0.0", port=server.port)
    except KeyboardInterrupt:
        print("\nServer stopped")


if __name__ == "__main__":
    main()
