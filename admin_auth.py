"""
Simple admin authentication for management endpoints
"""
import os
import hashlib
import secrets
from functools import wraps
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)

class AdminAuth:
    """Simple admin authentication system"""
    
    def __init__(self):
        # Get admin token from environment or generate one
        self.admin_token = os.environ.get('ADMIN_TOKEN')
        if not self.admin_token:
            self.admin_token = self._generate_admin_token()
            logger.warning(f"No ADMIN_TOKEN set. Generated temporary token: {self.admin_token}")
    
    def _generate_admin_token(self) -> str:
        """Generate a secure admin token"""
        return secrets.token_urlsafe(32)
    
    def require_admin_auth(self, f):
        """Decorator to require admin authentication"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for admin token in headers
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                logger.warning(f"Admin endpoint accessed without auth: {request.endpoint} from {request.remote_addr}")
                return jsonify({'error': 'Admin authentication required'}), 401
            
            # Extract token from "Bearer <token>" format
            try:
                scheme, token = auth_header.split(' ', 1)
                if scheme.lower() != 'bearer':
                    raise ValueError("Invalid scheme")
            except ValueError:
                logger.warning(f"Invalid auth header format: {request.endpoint} from {request.remote_addr}")
                return jsonify({'error': 'Invalid authentication format'}), 401
            
            # Validate token
            if not self._validate_token(token):
                logger.warning(f"Invalid admin token used: {request.endpoint} from {request.remote_addr}")
                return jsonify({'error': 'Invalid admin token'}), 401
            
            logger.info(f"Admin endpoint accessed: {request.endpoint} from {request.remote_addr}")
            return f(*args, **kwargs)
        
        return decorated_function
    
    def _validate_token(self, token: str) -> bool:
        """Validate admin token"""
        if not token or not self.admin_token:
            return False
        
        # Use secure comparison to prevent timing attacks
        return secrets.compare_digest(token, self.admin_token)
    
    def get_token_info(self) -> dict:
        """Get information about the admin token (for setup)"""
        return {
            'token_set': bool(self.admin_token),
            'token_source': 'environment' if os.environ.get('ADMIN_TOKEN') else 'generated',
            'token_length': len(self.admin_token) if self.admin_token else 0,
            'usage_example': 'curl -H "Authorization: Bearer YOUR_TOKEN" https://your-app.com/storage-stats'
        }

# Global admin auth instance
admin_auth = AdminAuth()

def require_admin(f):
    """Shortcut decorator for admin authentication"""
    return admin_auth.require_admin_auth(f)