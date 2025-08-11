###############################################################################
# MAIN APPLICATION ENTRY POINT
# Flask web server with enterprise security, performance optimization, and modular architecture
###############################################################################

from flask import Flask, render_template, request, jsonify
import os
import secrets
import logging
from datetime import timedelta, datetime
import re

from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_compress import Compress
import bleach

from modules.monthly_statements.monthly_statements import monthly_statements_bp
from modules.invoices.invoices import invoices_bp
from modules.excel_macros.excel_macros import excel_macros_bp
from modules.cc_batch.cc_batch import cc_batch_bp
from modules.help.help import help_bp
from modules.user_manual.user_manual import user_manual_bp

from cleanup_manager import cleanup_manager
from admin_auth import admin_auth, require_admin


###############################################################################
# APPLICATION CONFIGURATION
# Production-ready Flask app setup with security defaults
###############################################################################

app = Flask(__name__)

app.config.update({
    'SECRET_KEY': os.environ.get('SECRET_KEY', secrets.token_hex(32)),
    'WTF_CSRF_TIME_LIMIT': 3600,
    'MAX_CONTENT_LENGTH': 50 * 1024 * 1024,  # 50MB
    'SESSION_COOKIE_SECURE': os.environ.get('FLASK_ENV') == 'production',
    'SESSION_COOKIE_HTTPONLY': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
    'PERMANENT_SESSION_LIFETIME': timedelta(hours=2)
})


###############################################################################
# SECURITY MIDDLEWARE
# CSRF protection, rate limiting, security headers, compression
###############################################################################

csrf = CSRFProtect(app)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour", "10 per minute"],
    storage_uri="memory://"
)
limiter.init_app(app)

compress = Compress(app)

csp_config = {
    'default-src': "'self'",
    'script-src': "'self' 'unsafe-inline'",
    'style-src': "'self' 'unsafe-inline'", 
    'img-src': "'self' data:",
    'font-src': "'self'",
    'object-src': "'none'",
    'base-uri': "'self'",
    'frame-ancestors': "'none'"
}

talisman = Talisman(
    app,
    force_https=os.environ.get('FLASK_ENV') == 'production',
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy=csp_config,
    referrer_policy='strict-origin-when-cross-origin',
    feature_policy={'geolocation': "'none'", 'camera': "'none'", 'microphone': "'none'"}
)


###############################################################################
# LOGGING SETUP
# Application and security event logging
###############################################################################

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()]
)


###############################################################################
# INPUT VALIDATION UTILITIES
# O(1) session validation and O(n) input sanitization
###############################################################################

def validate_session_id(session_id):
    """Validate session ID format - O(1) complexity"""
    if not session_id or not isinstance(session_id, str) or len(session_id) > 50:
        return False
    return bool(re.match(r'^session_\d{8}_\d{6}$', session_id))

def sanitize_input(text):
    """Sanitize user input - O(n) complexity where n is text length"""
    return bleach.clean(str(text or ""), tags=[], attributes={}, strip=True)


###############################################################################
# ERROR HANDLERS
# Secure error responses that don't leak information
###############################################################################

@app.errorhandler(404)
def not_found(error):
    logging.warning(f"404 error: {request.url}")
    return render_template('base.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logging.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(413)
def file_too_large(error):
    return jsonify({'error': 'File too large. Maximum size is 50MB.'}), 413


###############################################################################
# BLUEPRINT REGISTRATION
# Modular feature registration with rate limiting exemptions
###############################################################################

blueprints = [
    (monthly_statements_bp, '/monthly_statements'),
    (invoices_bp, '/invoices'),
    (excel_macros_bp, '/excel_macros'),
    (cc_batch_bp, '/cc_batch'),
    (help_bp, '/help'),
    (user_manual_bp, '/user_manual')
]

for blueprint, prefix in blueprints:
    limiter.exempt(blueprint)
    app.register_blueprint(blueprint, url_prefix=prefix)


###############################################################################
# MAIN ROUTES
# Core application endpoints
###############################################################################

@app.route('/')
@limiter.limit("30 per minute")
def home():
    return render_template('index.html')


###############################################################################
# SYSTEM MONITORING
# Health checks and status endpoints
###############################################################################

@app.route('/health')
@limiter.exempt
def health_check():
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'app': 'AlaeAutomates 2.0',
        'version': '2.0.0'
    }
    if request.headers.get('X-Keep-Alive') == 'true':
        health_data['keep_alive'] = True
    return jsonify(health_data), 200

@app.route('/ping')
@limiter.limit("30 per minute")
def ping():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


###############################################################################
# ADMIN ENDPOINTS
# Administrative functionality with authentication
###############################################################################

@app.route('/storage-stats')
@limiter.limit("10 per minute")
@require_admin
def storage_stats():
    return jsonify(cleanup_manager.get_storage_stats())

@app.route('/cleanup', methods=['POST'])
@limiter.limit("2 per hour")
@require_admin
def manual_cleanup():
    try:
        stats = cleanup_manager.manual_cleanup()
        return jsonify({'status': 'success', 'stats': stats})
    except Exception as e:
        logging.error(f"Manual cleanup failed: {e}")
        return jsonify({'error': 'Cleanup failed'}), 500

@app.route('/admin-info')
@limiter.limit("5 per minute")
def admin_info():
    return jsonify(admin_auth.get_token_info())


###############################################################################
# APPLICATION STARTUP
# Initialize services and run application
###############################################################################

if __name__ == '__main__':
    for directory in ['uploads', 'results', 'separate_results']:
        os.makedirs(directory, exist_ok=True)
    
    cleanup_manager.start_background_cleanup()
    logging.info("Started automatic file cleanup manager")
    
    is_production = os.environ.get('FLASK_ENV') == 'production'
    port = int(os.environ.get('PORT', 5000))
    
    logging.info(f"Starting AlaeAutomates 2.0 on port {port} (production={is_production})")
    app.run(host='0.0.0.0', port=port, debug=not is_production)