"""
Security utilities and validation functions
"""
import os
import re
import logging
import mimetypes
import time
from functools import wraps
from typing import Optional, List, Dict, Any
from flask import request, jsonify, current_app
import bleach
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage

# Configure logging
logger = logging.getLogger(__name__)

class SecurityConfig:
    """Security configuration constants"""
    
    # File validation
    MAX_FILENAME_LENGTH = 255
    ALLOWED_EXTENSIONS = {
        'pdf': ['application/pdf'],
        'excel': [
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ]
    }
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    # Path traversal prevention
    FORBIDDEN_PATTERNS = [
        r'\.\.',  # Directory traversal
        r'[<>:"|?*]',  # Windows reserved characters
        r'[\x00-\x1f]',  # Control characters
        r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$'  # Windows reserved names
    ]
    
    # Session validation
    SESSION_ID_PATTERN = r'^session_\d{8}_\d{6}$'
    MAX_SESSION_ID_LENGTH = 50
    
    # Rate limiting bypass paths (for static resources)
    RATE_LIMIT_BYPASS = ['/static/', '/health']

def validate_filename(filename: str) -> bool:
    """Validate filename for security"""
    if not filename or len(filename) > SecurityConfig.MAX_FILENAME_LENGTH:
        return False
    
    # Check for forbidden patterns
    for pattern in SecurityConfig.FORBIDDEN_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            return False
    
    return True

def validate_file_content(file: FileStorage, allowed_types: List[str]) -> Dict[str, Any]:
    """Validate file content type and size"""
    result = {
        'valid': False,
        'error': None,
        'mime_type': None
    }
    
    # Check file size
    if hasattr(file, 'content_length') and file.content_length > SecurityConfig.MAX_FILE_SIZE:
        result['error'] = f'File too large. Maximum size is {SecurityConfig.MAX_FILE_SIZE // (1024*1024)}MB'
        return result
    
    # Check MIME type
    if file.filename:
        mime_type, _ = mimetypes.guess_type(file.filename)
        result['mime_type'] = mime_type
        
        if mime_type in allowed_types:
            result['valid'] = True
        else:
            result['error'] = f'Invalid file type. Allowed types: {", ".join(allowed_types)}'
    else:
        result['error'] = 'No filename provided'
    
    return result

def validate_session_id(session_id: str) -> bool:
    """Validate session ID format and content"""
    if not session_id or not isinstance(session_id, str):
        logger.warning(f"Invalid session ID type: {type(session_id)}")
        return False
    
    if len(session_id) > SecurityConfig.MAX_SESSION_ID_LENGTH:
        logger.warning(f"Session ID too long: {len(session_id)}")
        return False
    
    if not re.match(SecurityConfig.SESSION_ID_PATTERN, session_id):
        logger.warning(f"Session ID format invalid: {session_id}")
        return False
    
    return True

def sanitize_input(text: str, allow_html: bool = False) -> str:
    """Sanitize user input"""
    if not text:
        return ""
    
    # Convert to string and limit length
    text = str(text)[:10000]  # Prevent DoS through large inputs
    
    if allow_html:
        # Allow limited HTML tags
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li']
        allowed_attributes = {}
    else:
        # Strip all HTML
        allowed_tags = []
        allowed_attributes = {}
    
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attributes, strip=True)

def sanitize_path(path: str, base_dir: str) -> Optional[str]:
    """Sanitize file paths and prevent directory traversal"""
    if not path:
        return None
    
    # Normalize the path
    normalized_path = os.path.normpath(path)
    
    # Check for directory traversal attempts
    if '..' in normalized_path or normalized_path.startswith('/'):
        logger.warning(f"Directory traversal attempt detected: {path}")
        return None
    
    # Ensure path is within base directory
    full_path = os.path.abspath(os.path.join(base_dir, normalized_path))
    base_path = os.path.abspath(base_dir)
    
    if not full_path.startswith(base_path):
        logger.warning(f"Path outside base directory: {full_path}")
        return None
    
    return full_path

def validate_upload_files(pdf_file: FileStorage, excel_file: FileStorage) -> Dict[str, Any]:
    """Comprehensive file upload validation"""
    result = {
        'valid': True,
        'errors': []
    }
    
    # Check if files exist
    if not pdf_file or not pdf_file.filename:
        result['errors'].append('PDF file is required')
        result['valid'] = False
    
    if not excel_file or not excel_file.filename:
        result['errors'].append('Excel file is required')
        result['valid'] = False
    
    if not result['valid']:
        return result
    
    # Validate PDF file
    if not validate_filename(pdf_file.filename):
        result['errors'].append('Invalid PDF filename')
        result['valid'] = False
    
    pdf_validation = validate_file_content(pdf_file, SecurityConfig.ALLOWED_EXTENSIONS['pdf'])
    if not pdf_validation['valid']:
        result['errors'].append(f"PDF validation failed: {pdf_validation['error']}")
        result['valid'] = False
    
    # Validate Excel file
    if not validate_filename(excel_file.filename):
        result['errors'].append('Invalid Excel filename')
        result['valid'] = False
    
    excel_validation = validate_file_content(excel_file, SecurityConfig.ALLOWED_EXTENSIONS['excel'])
    if not excel_validation['valid']:
        result['errors'].append(f"Excel validation failed: {excel_validation['error']}")
        result['valid'] = False
    
    return result

def secure_error_response(error_msg: str, status_code: int = 500) -> tuple:
    """Return a secure error response that doesn't leak information"""
    
    # Log the actual error
    logger.error(f"Error: {error_msg}")
    
    # Generic error messages for different status codes
    generic_messages = {
        400: 'Bad request',
        401: 'Unauthorized',
        403: 'Forbidden', 
        404: 'Resource not found',
        413: 'File too large',
        422: 'Invalid input',
        429: 'Too many requests',
        500: 'Internal server error',
        503: 'Service unavailable'
    }
    
    public_message = generic_messages.get(status_code, 'An error occurred')
    
    # Only show actual error in development
    if current_app and current_app.debug:
        public_message = error_msg
    
    return jsonify({'error': public_message}), status_code

def require_valid_session(f):
    """Decorator to validate session ID in routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session_id = kwargs.get('session_id')
        if not validate_session_id(session_id):
            return secure_error_response('Invalid session', 400)
        return f(*args, **kwargs)
    return decorated_function

def log_security_event(event_type: str, details: Dict[str, Any]):
    """Log security-related events"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    user_agent = request.headers.get('User-Agent', 'unknown')
    
    log_data = {
        'event': event_type,
        'ip': client_ip,
        'user_agent': user_agent,
        'path': request.path,
        'details': details
    }
    
    logger.warning(f"Security event: {log_data}")

class SecureSessionManager:
    """Thread-safe session management with automatic cleanup"""
    
    def __init__(self):
        self._sessions = {}
        self._session_timeouts = {}
    
    def create_session(self, session_id: str, data: Any) -> bool:
        """Create a new session"""
        if not validate_session_id(session_id):
            return False
        
        self._sessions[session_id] = data
        self._session_timeouts[session_id] = time.time() + 7200  # 2 hours
        return True
    
    def get_session(self, session_id: str) -> Optional[Any]:
        """Get session data"""
        if not validate_session_id(session_id):
            return None
        
        # Check if session exists and hasn't expired
        if session_id not in self._sessions:
            return None
        
        if time.time() > self._session_timeouts.get(session_id, 0):
            self.delete_session(session_id)
            return None
        
        return self._sessions.get(session_id)
    
    def update_session(self, session_id: str, data: Any) -> bool:
        """Update session data"""
        if session_id not in self._sessions:
            return False
        
        self._sessions[session_id] = data
        self._session_timeouts[session_id] = time.time() + 7200  # Reset timeout
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        deleted = False
        if session_id in self._sessions:
            del self._sessions[session_id]
            deleted = True
        if session_id in self._session_timeouts:
            del self._session_timeouts[session_id]
        return deleted
    
    def cleanup_expired(self):
        """Clean up expired sessions"""
        current_time = time.time()
        expired = [sid for sid, timeout in self._session_timeouts.items() if current_time > timeout]
        for session_id in expired:
            self.delete_session(session_id)
        return len(expired)

# Global secure session manager instance
secure_session_manager = SecureSessionManager()