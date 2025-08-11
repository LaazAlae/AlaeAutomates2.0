from flask import Flask, render_template, request, jsonify, session
import os
import secrets
import logging
from datetime import timedelta, datetime
import re

# Security imports
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_compress import Compress
import bleach

# Import module blueprints
from modules.monthly_statements.monthly_statements import monthly_statements_bp
from modules.invoices.invoices import invoices_bp
from modules.excel_macros.excel_macros import excel_macros_bp
from modules.cc_batch.cc_batch import cc_batch_bp
from modules.help.help import help_bp
from modules.user_manual.user_manual import user_manual_bp

# Import cleanup manager and admin auth
from cleanup_manager import cleanup_manager
from admin_auth import admin_auth, require_admin

app = Flask(__name__)

# Security Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# Initialize security extensions
csrf = CSRFProtect(app)
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour", "10 per minute"],
    storage_uri="memory://"
)
limiter.init_app(app)

# Initialize performance extensions
compress = Compress(app)

# Security Headers with Talisman
csp = {
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
    content_security_policy=csp,
    referrer_policy='strict-origin-when-cross-origin',
    feature_policy={
        'geolocation': "'none'",
        'camera': "'none'",
        'microphone': "'none'",
    }
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

# Input validation functions
def validate_session_id(session_id):
    """Validate session ID format"""
    if not session_id or not isinstance(session_id, str):
        return False
    pattern = r'^session_\d{8}_\d{6}$'
    return bool(re.match(pattern, session_id)) and len(session_id) <= 50

def sanitize_input(text):
    """Sanitize user input"""
    if not text:
        return ""
    return bleach.clean(str(text), tags=[], attributes={}, strip=True)

# Error handlers
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

# Register blueprints with CSRF and rate limiting
limiter.exempt(monthly_statements_bp)
limiter.exempt(invoices_bp)
limiter.exempt(excel_macros_bp)
limiter.exempt(cc_batch_bp) 
limiter.exempt(help_bp)
limiter.exempt(user_manual_bp)

app.register_blueprint(monthly_statements_bp, url_prefix='/monthly_statements')
app.register_blueprint(invoices_bp, url_prefix='/invoices')
app.register_blueprint(excel_macros_bp, url_prefix='/excel_macros')
app.register_blueprint(cc_batch_bp, url_prefix='/cc_batch')
app.register_blueprint(help_bp, url_prefix='/help')
app.register_blueprint(user_manual_bp, url_prefix='/user_manual')

@app.route('/')
@limiter.limit("30 per minute")
def home():
    return render_template('index.html')

# Enhanced health check endpoint
@app.route('/health')
@limiter.exempt
def health_check():
    # Check if this is a keep-alive ping
    is_keep_alive = request.headers.get('X-Keep-Alive') == 'true'
    
    health_data = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'app': 'AlaeAutomates 2.0',
        'version': '2.0.0'
    }
    
    if is_keep_alive:
        health_data['keep_alive'] = True
        
    return jsonify(health_data), 200

# Storage stats endpoint (admin only)
@app.route('/storage-stats')
@limiter.limit("10 per minute")
@require_admin
def storage_stats():
    stats = cleanup_manager.get_storage_stats()
    return jsonify(stats)

# Manual cleanup endpoint (admin only)
@app.route('/cleanup', methods=['POST'])
@limiter.limit("2 per hour")
@require_admin
def manual_cleanup():
    try:
        stats = cleanup_manager.manual_cleanup()
        return jsonify({
            'status': 'success',
            'stats': stats
        })
    except Exception as e:
        logging.error(f"Manual cleanup failed: {e}")
        return jsonify({'error': 'Cleanup failed'}), 500

# Health check endpoint for monitoring
@app.route('/ping', methods=['GET'])
@limiter.limit("30 per minute")
def ping():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

# Admin token info endpoint (for setup)
@app.route('/admin-info')
@limiter.limit("5 per minute")
def admin_info():
    info = admin_auth.get_token_info()
    return jsonify(info)

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('results', exist_ok=True)
    os.makedirs('separate_results', exist_ok=True)
    
    # Start background services
    cleanup_manager.start_background_cleanup()
    logging.info("Started automatic file cleanup manager")
    
    # Production vs Development
    debug_mode = os.environ.get('FLASK_ENV') != 'production'
    port = int(os.environ.get('PORT', 5000))
    
    # Log startup info
    logging.info(f"Starting AlaeAutomates 2.0 on port {port} (debug={debug_mode})")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)