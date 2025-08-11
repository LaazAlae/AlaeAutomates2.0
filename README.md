# AlaeAutomates 2.0

A production-ready document processing automation platform with enterprise-grade security, optimized performance, and modular architecture designed for scalability and maintainability.

## Features

### Document Processing Modules

**Monthly Statements Processing**
- Intelligent PDF text extraction and transaction categorization
- Cross-reference validation with Excel data sources
- Interactive manual review system for ambiguous entries
- Automated generation of categorized Excel outputs
- Background processing to handle large documents without timeouts

**Invoice Processing & Separation**
- Batch processing of multi-invoice PDF documents
- Pattern recognition for invoice number extraction (P/R + 6-8 digits)
- Automatic document splitting with page grouping
- Structured Excel reporting for accounting system integration

**Excel Macro Generation**
- Clean-up and formatting automation (empty row/column removal, whitespace trimming)
- Sort and sum operations with intelligent column detection
- VBA code generation with installation instructions
- Custom macro development for repetitive data processing tasks

**Credit Card Batch Automation**
- JavaScript generation for automated form filling
- Payment processing workflow automation
- Data validation and formatting for financial systems
- Browser console integration for web-based payment platforms

### Security Architecture

**Multi-Layered Defense System**
- CSRF protection with token-based validation
- Aggressive rate limiting (200/day, 50/hour, 10/minute)
- XSS prevention through comprehensive input sanitization
- Directory traversal protection with path validation
- Secure session management with automatic expiration

**File Upload Security**
- MIME type validation with size limits (50MB maximum)
- Filename security checks against injection patterns
- Secure file handling with restricted permissions
- Automatic cleanup to prevent storage accumulation

**Security Headers & Compliance**
- HSTS enforcement for HTTPS connections
- Content Security Policy (CSP) implementation
- X-Frame-Options for clickjacking protection
- Referrer policy controls for information leakage
- Feature policy restrictions for unnecessary browser capabilities

## Technical Architecture

### Core Components

**Main Application** (`main_app.py`)
- Flask web server with security middleware integration
- Modular blueprint architecture for feature separation
- Production-ready configuration with environment-based settings
- Comprehensive error handling and logging

**Security Module** (`security.py`)
- O(1) complexity validation functions for performance
- Thread-safe session management with automatic cleanup
- Input sanitization preventing XSS and injection attacks
- Secure error responses that prevent information disclosure

**Cleanup Manager** (`cleanup_manager.py`)
- Automated file lifecycle management
- Age-based cleanup (24-hour retention by default)
- Size-based cleanup (100MB storage limit enforcement)
- Orphaned session file removal
- Background processing with configurable intervals

**Admin Authentication** (`admin_auth.py`)
- Bearer token-based authentication system
- Timing attack protection using secure comparison
- Administrative endpoint protection
- Token generation and management utilities

### Performance Optimizations

**Algorithm Complexity**
- O(1) session validation and security checks
- O(n) file processing that scales linearly with input size
- O(n log n) size-based cleanup with efficient sorting
- Background threading for non-blocking operations

**Resource Management**
- Automatic file cleanup prevents storage accumulation
- Memory-efficient file processing with streaming
- Compression middleware for bandwidth optimization
- Configurable rate limiting for resource protection

## Quick Start

### Local Development

```bash
# Clone and setup
git clone https://github.com/LaazAlae/AlaeAutomates2.0.git
cd AlaeAutomates2.0

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run application
python main_app.py
```

Application runs at `http://localhost:5000`

### Production Deployment

#### Railway Hosting

1. **Repository Setup**
   - Ensure `requirements.txt` and `railway.json` are present
   - Configure environment variables in Railway dashboard

2. **Deployment Process**
   - Connect GitHub repository to Railway
   - Railway automatically detects Flask application
   - Application runs on Railway-specified PORT environment variable

3. **Required Environment Variables**
   ```
   FLASK_ENV=production
   SECRET_KEY=<32-character-secure-key>
   ADMIN_TOKEN=<secure-admin-token>
   ```

## API Endpoints

### Public Endpoints
- `GET /` - Main application interface
- `GET /health` - Health check and monitoring
- `GET /ping` - Simple status verification

### Feature Module Endpoints
- `/monthly_statements/` - Statement processing workflows
- `/invoices/` - Invoice processing and separation
- `/excel_macros/` - Excel macro generation
- `/cc_batch/` - Credit card batch automation
- `/help/` - Built-in documentation system
- `/user_manual/` - Comprehensive user guide

### Administrative Endpoints (Authentication Required)
- `GET /storage-stats` - Storage usage monitoring
- `POST /cleanup` - Manual cleanup triggers
- `GET /admin-info` - Token configuration information

## Adding New Features

### Module Structure

The application follows a modular blueprint architecture for easy extensibility:

```
modules/
└── new_feature/
    ├── new_feature.py          # Blueprint implementation
    ├── templates/
    │   └── new_feature/        # Feature-specific templates
    └── static/                 # Feature-specific assets (optional)
```

### Implementation Steps

1. **Create Blueprint Module**
   ```python
   # modules/new_feature/new_feature.py
   from flask import Blueprint, render_template, request
   
   new_feature_bp = Blueprint('new_feature', __name__, template_folder='templates')
   
   @new_feature_bp.route('/')
   def index():
       return render_template('new_feature/index.html')
   ```

2. **Register in Main Application**
   ```python
   # main_app.py - Add to blueprints list
   from modules.new_feature.new_feature import new_feature_bp
   
   blueprints = [
       # ... existing blueprints
       (new_feature_bp, '/new_feature')
   ]
   ```

3. **Security Integration**
   - Use `security.py` functions for input validation
   - Implement `validate_upload_files()` for file uploads
   - Apply `sanitize_input()` for user data processing
   - Add rate limiting as needed

4. **Template Integration**
   - Extend `base.html` for consistent styling
   - Follow existing UI patterns and components
   - Implement CSRF protection in forms

### Best Practices

**Security Considerations**
- Always validate and sanitize user inputs
- Implement appropriate rate limiting for new endpoints
- Use secure file handling for uploads
- Log security events using `log_security_event()`

**Performance Guidelines**
- Optimize for O(1) or O(n) complexity where possible
- Use background processing for long-running operations
- Implement proper error handling and logging
- Consider memory usage for large file operations

**Code Organization**
- Follow the established section structure with `###` headers
- Include complexity analysis in function docstrings
- Maintain consistent naming conventions
- Add comprehensive error handling

## Development Environment

### File Structure
```
AlaeAutomates2.0/
├── main_app.py              # Main Flask application
├── security.py              # Security utilities
├── cleanup_manager.py       # File management
├── admin_auth.py            # Authentication
├── requirements.txt         # Dependencies
├── railway.json             # Deployment config
├── modules/                 # Feature modules
├── templates/               # Jinja2 templates
├── static/                  # CSS and assets
├── uploads/                 # Temporary uploads
├── results/                 # Processing results
└── separate_results/        # Additional outputs
```

### Code Quality Standards

**Security First**
- All code follows OWASP security guidelines
- Input validation on every user interaction
- Secure defaults in all configurations
- Regular security auditing and updates

**Performance Optimized**
- Efficient algorithms with documented complexity
- Resource-conscious file handling
- Background processing for user experience
- Automated cleanup for resource management

**Maintainable Architecture**
- Clear separation of concerns between modules
- Comprehensive documentation and comments
- Consistent error handling patterns
- Modular design supporting easy feature addition

## Monitoring and Maintenance

### Health Monitoring
- `/health` endpoint provides detailed application status
- Background services with automatic restart capability
- File cleanup operations with configurable schedules
- Storage usage tracking and alerting

### Security Monitoring
- Authentication attempt logging with IP tracking
- File upload validation and security event logging
- Rate limit violation tracking and response
- Admin access logging for audit trails

### Performance Monitoring
- Request rate limiting prevents system abuse
- Background processing prevents timeout issues
- Automatic file cleanup maintains optimal performance
- Resource usage statistics through admin endpoints

## Support and Documentation

The application includes comprehensive built-in documentation accessible through the `/help` and `/user_manual` endpoints, providing detailed guidance for both end users and administrators.