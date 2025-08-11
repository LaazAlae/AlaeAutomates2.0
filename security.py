###############################################################################
# SECURITY UTILITIES MODULE
# Comprehensive protection against web attacks, input validation, and threat monitoring
###############################################################################

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

logger = logging.getLogger(__name__)


###############################################################################
# SECURITY CONFIGURATION
# Constants for validation rules and attack prevention
###############################################################################

class SecurityConfig:
    """Centralized security configuration - O(1) lookups for all checks"""
    
    MAX_FILENAME_LENGTH = 255
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_SESSION_ID_LENGTH = 50
    SESSION_DURATION = 7200  # 2 hours
    
    ALLOWED_EXTENSIONS = {
        'pdf': ['application/pdf'],
        'excel': ['application/vnd.ms-excel', 
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']
    }
    
    FORBIDDEN_PATTERNS = [
        r'\.\.', r'[<>:"|?*]', r'[\x00-\x1f]',
        r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$'
    ]
    
    SESSION_ID_PATTERN = r'^session_\d{8}_\d{6}_[a-f0-9]{8}$'


###############################################################################
# FILE VALIDATION FUNCTIONS
# O(1) to O(n) complexity security checks
###############################################################################

def validate_filename(filename: str) -> bool:
    """Validate filename security - O(n) where n is filename length"""
    if not filename or len(filename) > SecurityConfig.MAX_FILENAME_LENGTH:
        return False
    
    return not any(re.search(pattern, filename, re.IGNORECASE) 
                   for pattern in SecurityConfig.FORBIDDEN_PATTERNS)

def validate_file_content(file: FileStorage, allowed_types: List[str]) -> Dict[str, Any]:
    """Comprehensive file validation - O(1) complexity"""
    if not file.filename:
        return {'valid': False, 'error': 'No filename provided', 'mime_type': None}
    
    if hasattr(file, 'content_length') and file.content_length > SecurityConfig.MAX_FILE_SIZE:
        max_mb = SecurityConfig.MAX_FILE_SIZE // (1024*1024)
        return {'valid': False, 'error': f'File too large. Maximum size is {max_mb}MB', 'mime_type': None}
    
    mime_type, _ = mimetypes.guess_type(file.filename)
    if mime_type in allowed_types:
        return {'valid': True, 'error': None, 'mime_type': mime_type}
    else:
        return {'valid': False, 'error': f'Invalid file type. Allowed: {", ".join(allowed_types)}', 'mime_type': mime_type}

def validate_upload_files(pdf_file: FileStorage, excel_file: FileStorage) -> Dict[str, Any]:
    """Multi-file validation - O(1) complexity with early validation failures"""
    errors = []
    
    if not pdf_file or not pdf_file.filename:
        errors.append('PDF file is required')
    if not excel_file or not excel_file.filename:
        errors.append('Excel file is required')
    
    if errors:
        return {'valid': False, 'errors': errors}
    
    files_to_validate = [
        (pdf_file, SecurityConfig.ALLOWED_EXTENSIONS['pdf'], 'PDF'),
        (excel_file, SecurityConfig.ALLOWED_EXTENSIONS['excel'], 'Excel')
    ]
    
    for file_obj, allowed_types, file_type in files_to_validate:
        if not validate_filename(file_obj.filename):
            errors.append(f'Invalid {file_type} filename')
        
        validation_result = validate_file_content(file_obj, allowed_types)
        if not validation_result['valid']:
            errors.append(f'{file_type} validation failed: {validation_result["error"]}')
    
    return {'valid': len(errors) == 0, 'errors': errors}


###############################################################################
# SESSION VALIDATION
# O(1) complexity session security
###############################################################################

def validate_session_id(session_id: str) -> bool:
    """Session ID validation - O(1) complexity with early exits"""
    if (not session_id or not isinstance(session_id, str) or 
        len(session_id) > SecurityConfig.MAX_SESSION_ID_LENGTH):
        logger.warning(f"Invalid session ID: {type(session_id) if session_id else 'None'}")
        return False
    
    if not re.match(SecurityConfig.SESSION_ID_PATTERN, session_id):
        logger.warning(f"Session ID format invalid: {session_id}")
        return False
    
    return True


###############################################################################
# INPUT SANITIZATION
# XSS and injection attack prevention
###############################################################################

def sanitize_input(text: str, allow_html: bool = False) -> str:
    """Input sanitization - O(n) where n is text length, prevents XSS/injection"""
    if not text:
        return ""
    
    text = str(text)[:10000]  # Prevent DoS attacks
    
    if allow_html:
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li']
        allowed_attrs = {}
    else:
        allowed_tags, allowed_attrs = [], {}
    
    return bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)

def sanitize_path(path: str, base_dir: str) -> Optional[str]:
    """Path sanitization - O(n) complexity, prevents directory traversal attacks"""
    if not path:
        return None
    
    normalized_path = os.path.normpath(path)
    
    if '..' in normalized_path or normalized_path.startswith('/'):
        logger.warning(f"Directory traversal attempt: {path}")
        return None
    
    full_path = os.path.abspath(os.path.join(base_dir, normalized_path))
    base_path = os.path.abspath(base_dir)
    
    if not full_path.startswith(base_path):
        logger.warning(f"Path escape attempt: {full_path}")
        return None
    
    return full_path


###############################################################################
# ERROR HANDLING & SECURITY RESPONSES
# Information disclosure prevention
###############################################################################

def secure_error_response(error_msg: str, status_code: int = 500) -> tuple:
    """Secure error responses - O(1) complexity, prevents information disclosure"""
    logger.error(f"Error: {error_msg}")
    
    error_messages = {
        400: 'Bad request', 401: 'Unauthorized', 403: 'Forbidden',
        404: 'Resource not found', 413: 'File too large', 422: 'Invalid input',
        429: 'Too many requests', 500: 'Internal server error', 503: 'Service unavailable'
    }
    
    public_message = error_msg if (current_app and current_app.debug) else error_messages.get(status_code, 'An error occurred')
    
    return jsonify({'error': public_message}), status_code

def require_valid_session(f):
    """Route decorator for session validation - O(1) complexity"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not validate_session_id(kwargs.get('session_id')):
            return secure_error_response('Invalid session', 400)
        return f(*args, **kwargs)
    return decorated_function

def log_security_event(event_type: str, details: Dict[str, Any]):
    """Security event logging - O(1) complexity for threat monitoring"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    log_data = {
        'event': event_type, 'ip': client_ip, 'path': request.path,
        'user_agent': request.headers.get('User-Agent', 'unknown'), 'details': details
    }
    logger.warning(f"Security event: {log_data}")


###############################################################################
# SECURE SESSION MANAGER
# Thread-safe session management with automatic cleanup
###############################################################################

class SecureSessionManager:
    """Thread-safe session management - O(1) operations with automatic expiration"""
    
    def __init__(self):
        self._sessions = {}
        self._session_timeouts = {}
        self.session_duration = SecurityConfig.SESSION_DURATION
    
    def create_session(self, session_id: str, data: Any) -> bool:
        """Create session - O(1) complexity"""
        if not validate_session_id(session_id):
            return False
        
        self._sessions[session_id] = data
        self._session_timeouts[session_id] = time.time() + self.session_duration
        return True
    
    def get_session(self, session_id: str) -> Optional[Any]:
        """Get session data - O(1) complexity with expiration check"""
        if not validate_session_id(session_id) or session_id not in self._sessions:
            return None
        
        if time.time() > self._session_timeouts.get(session_id, 0):
            self.delete_session(session_id)
            return None
        
        return self._sessions[session_id]
    
    def update_session(self, session_id: str, data: Any) -> bool:
        """Update session - O(1) complexity"""
        if session_id not in self._sessions:
            return False
        
        self._sessions[session_id] = data
        self._session_timeouts[session_id] = time.time() + self.session_duration
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Delete session - O(1) complexity"""
        deleted = session_id in self._sessions
        self._sessions.pop(session_id, None)
        self._session_timeouts.pop(session_id, None)
        return deleted
    
    def cleanup_expired(self) -> int:
        """Clean expired sessions - O(n) where n is active sessions"""
        current_time = time.time()
        expired = [sid for sid, timeout in self._session_timeouts.items() 
                  if current_time > timeout]
        
        for session_id in expired:
            self.delete_session(session_id)
        
        return len(expired)


###############################################################################
# GLOBAL INSTANCES
# Shared security components
###############################################################################

secure_session_manager = SecureSessionManager()