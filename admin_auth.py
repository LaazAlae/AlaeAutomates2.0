###############################################################################
# ADMIN AUTHENTICATION MODULE
# Bearer token-based authentication for administrative endpoints
###############################################################################

import os
import secrets
from functools import wraps
from flask import request, jsonify
import logging

logger = logging.getLogger(__name__)


###############################################################################
# ADMIN AUTHENTICATION CLASS
# Secure token-based authentication with timing attack protection
###############################################################################

class AdminAuth:
    """Secure admin authentication system - O(1) token validation"""
    
    def __init__(self):
        self.admin_token = os.environ.get('ADMIN_TOKEN')
        if not self.admin_token:
            self.admin_token = secrets.token_urlsafe(32)
            logger.warning(f"No ADMIN_TOKEN set. Generated temporary token: {self.admin_token}")


###############################################################################
# AUTHENTICATION DECORATORS
# Route protection with secure token validation
###############################################################################

    def require_admin_auth(self, f):
        """Decorator to require admin authentication - O(1) complexity"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            if not auth_header:
                logger.warning(f"Admin endpoint accessed without auth: {request.endpoint} from {request.remote_addr}")
                return jsonify({'error': 'Admin authentication required'}), 401
            
            try:
                scheme, token = auth_header.split(' ', 1)
                if scheme.lower() != 'bearer':
                    raise ValueError("Invalid scheme")
            except ValueError:
                logger.warning(f"Invalid auth header format: {request.endpoint} from {request.remote_addr}")
                return jsonify({'error': 'Invalid authentication format'}), 401
            
            if not self._validate_token(token):
                logger.warning(f"Invalid admin token used: {request.endpoint} from {request.remote_addr}")
                return jsonify({'error': 'Invalid admin token'}), 401
            
            logger.info(f"Admin endpoint accessed: {request.endpoint} from {request.remote_addr}")
            return f(*args, **kwargs)
        
        return decorated_function

    def _validate_token(self, token: str) -> bool:
        """Validate admin token - O(1) complexity with timing attack protection"""
        if not token or not self.admin_token:
            return False
        return secrets.compare_digest(token, self.admin_token)


###############################################################################
# TOKEN INFORMATION
# Setup and configuration utilities
###############################################################################

    def get_token_info(self) -> dict:
        """Get information about the admin token for setup purposes"""
        return {
            'token_set': bool(self.admin_token),
            'token_source': 'environment' if os.environ.get('ADMIN_TOKEN') else 'generated',
            'token_length': len(self.admin_token) if self.admin_token else 0,
            'usage_example': 'curl -H "Authorization: Bearer YOUR_TOKEN" https://your-app.com/storage-stats'
        }


###############################################################################
# GLOBAL INSTANCES
# Shared authentication components
###############################################################################

admin_auth = AdminAuth()

def require_admin(f):
    """Shortcut decorator for admin authentication"""
    return admin_auth.require_admin_auth(f)