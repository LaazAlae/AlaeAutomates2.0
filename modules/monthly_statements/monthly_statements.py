from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_from_directory
import os
import shutil
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from werkzeug.utils import secure_filename
import tempfile
import zipfile

# Import existing processor from same directory
from .statement_processor import StatementProcessor

# Import security utilities
from security import (
    validate_upload_files, 
    validate_session_id, 
    sanitize_input,
    secure_error_response,
    require_valid_session,
    log_security_event,
    secure_session_manager
)

monthly_statements_bp = Blueprint('monthly_statements', __name__, template_folder='templates')

# Configuration
UPLOAD_FOLDER = os.path.abspath('uploads')
RESULT_FOLDER = os.path.abspath('results')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

class WebStatementProcessor:
    """Web interface wrapper for StatementProcessor"""
    
    def __init__(self, pdf_path: str, excel_path: str, session_id: str):
        self.processor = StatementProcessor(pdf_path, excel_path)
        self.session_id = session_id
        self.statements: List[Dict[str, Any]] = []
        self.current_question_index = 0
        self.questions_needed: List[Dict[str, Any]] = []
        self.user_responses: List[str] = []
        self.question_history: List[int] = []
        
        # Background processing status
        self._processing_status = 'pending'
        self._start_time = None
        self._processing_logs = []
        self._error_message = None
    
    def extract_statements(self) -> List[Dict[str, Any]]:
        """Extract statements from PDF"""
        self.statements = self.processor.extract_statements()
        return self.statements
    
    def start_background_extraction(self):
        """Start background statement extraction to prevent HTTP timeouts"""
        import threading
        import logging
        from datetime import datetime
        
        logger = logging.getLogger(__name__)
        
        def log_message(msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {msg}"
            logger.info(f"[{self.session_id}] {msg}")
            self._processing_logs.append(log_entry)
        
        def extract_in_background():
            try:
                log_message("Background extraction thread started")
                self._processing_status = 'processing'
                self._start_time = datetime.now()
                
                log_message("Starting PDF text extraction...")
                self.statements = self.processor.extract_statements()
                log_message(f"Extracted {len(self.statements)} statements successfully")
                
                log_message("Analyzing statements for manual review...")
                self.questions_needed = [stmt for stmt in self.statements if stmt.get('ask_question', False)]
                log_message(f"Found {len(self.questions_needed)} statements requiring manual review")
                
                self._processing_status = 'completed'
                log_message("Statement extraction completed successfully")
                
            except Exception as e:
                self._processing_status = 'error'
                self._error_message = str(e)
                log_message(f"ERROR: Statement extraction failed - {str(e)}")
                logger.error(f"[{self.session_id}] Background extraction failed", exc_info=True)
        
        # Initialize logging
        log_message("Initializing background statement extraction...")
        
        # Start background thread
        extraction_thread = threading.Thread(target=extract_in_background, daemon=True)
        extraction_thread.start()
        
        log_message("Background thread started, returning control to web interface")
    
    def get_questions(self) -> List[Dict[str, Any]]:
        """Get questions that need manual review"""
        self.questions_needed = [stmt for stmt in self.statements if stmt.get('ask_question', False)]
        return self.questions_needed
    
    def process_question_response(self, response: str) -> Dict[str, Any]:
        """Process a single question response"""
        if self.current_question_index >= len(self.questions_needed):
            return {"completed": True}
        
        statement = self.questions_needed[self.current_question_index]
        
        if response == 'y':
            self.question_history.append(self.current_question_index)
            statement['destination'] = 'DNM'
            statement['user_answered'] = 'yes'
            self.current_question_index += 1
        elif response == 'n':
            self.question_history.append(self.current_question_index)
            statement['user_answered'] = 'no'
            self.current_question_index += 1
        elif response == 's':
            for i in range(self.current_question_index, len(self.questions_needed)):
                self.questions_needed[i]['user_answered'] = 'skip'
            self.current_question_index = len(self.questions_needed)
        elif response == 'p':
            if self.question_history:
                self.current_question_index = self.question_history.pop()
            else:
                return {"error": "No previous questions"}
        
        return self.get_current_question_state()
    
    def get_current_question_state(self) -> Dict[str, Any]:
        """Get current question state"""
        if self.current_question_index >= len(self.questions_needed):
            return {"completed": True, "total": len(self.questions_needed)}
        
        statement = self.questions_needed[self.current_question_index]
        return {
            "completed": False,
            "current": self.current_question_index + 1,
            "total": len(self.questions_needed),
            "company_name": statement.get('company_name', 'Unknown'),
            "similar_to": statement.get('similar_to', 'Unknown'),
            "can_go_back": len(self.question_history) > 0
        }
    
    def create_results(self) -> Dict[str, Any]:
        """Create PDF results in background and return statistics immediately"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"[{self.session_id}] Starting create_results - JSON phase")
        
        # Save JSON results first (fast operation)
        today = datetime.now().strftime("%b%d%Y").lower()
        json_path = os.path.join(RESULT_FOLDER, f"{self.session_id}_{today}.json")
        
        counter = 1
        while os.path.exists(json_path):
            json_path = os.path.join(RESULT_FOLDER, f"{self.session_id}_{today}-{counter}.json")
            counter += 1
        
        logger.info(f"[{self.session_id}] JSON path determined: {json_path}")
        
        data = {
            "dnm_companies": self.processor.dnm_companies,
            "extracted_statements": self.statements,
            "total_statements_found": len(self.statements),
            "processing_timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"[{self.session_id}] Creating results directory...")
        os.makedirs(RESULT_FOLDER, exist_ok=True)
        
        logger.info(f"[{self.session_id}] Writing JSON file with {len(self.statements)} statements...")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"[{self.session_id}] JSON file written successfully")
        
        # Initialize logging list for this session
        if not hasattr(self, '_processing_logs'):
            self._processing_logs = []
        
        def log_message(msg):
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {msg}"
            logger.info(f"[{self.session_id}] {msg}")
            self._processing_logs.append(log_entry)
        
        # Start PDF creation in background thread (non-blocking)
        import threading
        import time
        
        def create_pdfs_async():
            try:
                log_message("Background PDF thread started")
                self._pdf_creation_status = 'creating'
                self._pdf_start_time = time.time()
                
                log_message(f"Starting PDF creation with {len(self.statements)} statements")
                
                # Create split PDFs
                log_message("Calling processor.create_split_pdfs()...")
                split_results = self.processor.create_split_pdfs(self.statements)
                log_message(f"PDF creation returned: {split_results}")
                
                # Move PDFs to results directory
                log_message("Moving PDFs to results directory...")
                pdf_files = {}
                for dest, pages in split_results.items():
                    old_file = {
                        "DNM": "DNM.pdf",
                        "Foreign": "Foreign.pdf", 
                        "Natio Single": "natioSingle.pdf",
                        "Natio Multi": "natioMulti.pdf"
                    }[dest]
                    
                    log_message(f"Processing {dest}: looking for {old_file} with {pages} pages")
                    
                    if os.path.exists(old_file):
                        new_file = os.path.join(RESULT_FOLDER, f"{self.session_id}_{old_file}")
                        log_message(f"Moving {old_file} to {new_file}")
                        shutil.move(old_file, new_file)
                        pdf_files[dest] = {"file": new_file, "pages": pages}
                        log_message(f"Successfully moved {dest} PDF")
                    else:
                        log_message(f"WARNING: {old_file} does not exist, skipping")
                
                self._pdf_files = pdf_files
                self._pdf_creation_status = 'completed'
                self._pdf_end_time = time.time()
                
                elapsed = self._pdf_end_time - self._pdf_start_time
                log_message(f"PDF creation completed successfully in {elapsed:.1f} seconds")
                log_message(f"Created {len(pdf_files)} PDF files: {list(pdf_files.keys())}")
                
            except Exception as e:
                self._pdf_creation_status = 'error' 
                self._pdf_error = str(e)
                log_message(f"ERROR in PDF creation: {str(e)}")
                logger.error(f"[{self.session_id}] PDF creation failed", exc_info=True)
        
        # Initialize status tracking
        log_message("Initializing PDF creation status tracking")
        self._pdf_creation_status = 'starting'
        self._pdf_files = {}
        
        # Start background thread
        log_message("Starting background PDF creation thread...")
        pdf_thread = threading.Thread(target=create_pdfs_async, daemon=True)
        pdf_thread.start()
        log_message("Background thread started, continuing with response")
        
        # Calculate statistics (fast operation)
        logger.info(f"[{self.session_id}] Calculating statistics...")
        stats = self.calculate_statistics()
        logger.info(f"[{self.session_id}] Statistics calculated")
        
        logger.info(f"[{self.session_id}] create_results completing, returning response")
        
        # Return immediately without waiting for PDFs
        return {
            "pdf_files": {},  # Will be populated asynchronously
            "json_file": json_path,
            "statistics": stats,
            "pdf_status": "creating"  # Indicate PDFs are being created
        }
    
    def calculate_statistics(self) -> Dict[str, Any]:
        """Calculate processing statistics"""
        destinations = {}
        manual_count = 0
        ask_count = 0
        auto_dnm_reasons = {"exact": 0, "email": 0, "high_confidence": 0}
        
        for stmt in self.statements:
            dest = stmt.get('destination', 'Unknown')
            destinations[dest] = destinations.get(dest, 0) + 1
            
            if stmt.get('manual_required', False):
                manual_count += 1
            if stmt.get('ask_question', False):
                ask_count += 1
            
            # Count auto-DNM reasons
            if dest == "DNM":
                if stmt.get('exact_match'):
                    auto_dnm_reasons["exact"] += 1
                elif "email" in stmt.get('rest_of_lines', '').lower():
                    auto_dnm_reasons["email"] += 1
                else:
                    percentage = stmt.get('percentage', '')
                    if percentage:
                        try:
                            if float(percentage.replace('%', '')) >= 90.0:
                                auto_dnm_reasons["high_confidence"] += 1
                        except ValueError:
                            pass
        
        return {
            "total_statements": len(self.statements),
            "destinations": destinations,
            "dnm_breakdown": auto_dnm_reasons,
            "manual_processing": {
                "manual_review_required": manual_count,
                "interactive_questions": ask_count
            }
        }

@monthly_statements_bp.route('/')
def monthly_statements():
    return render_template('monthly_statements/upload.html')

@monthly_statements_bp.route('/process', methods=['POST'])
def process_files():
    try:
        # Validate CSRF token is handled by Flask-WTF automatically
        
        # Check if files are present
        if 'pdf_file' not in request.files or 'excel_file' not in request.files:
            log_security_event('missing_files', {'missing': 'pdf_file or excel_file'})
            return secure_error_response('Both PDF and Excel files are required', 400)
        
        pdf_file = request.files['pdf_file']
        excel_file = request.files['excel_file']
        
        # Check file sizes for optimal processing
        pdf_size_mb = len(pdf_file.read()) / (1024 * 1024)
        pdf_file.seek(0)  # Reset file pointer
        
        if pdf_size_mb > 50:  # Vercel supports larger files
            log_security_event('file_too_large', {'size_mb': pdf_size_mb})
            return secure_error_response(f'PDF file too large ({pdf_size_mb:.1f}MB). Maximum size is 50MB.', 413)
        
        # Comprehensive file validation
        validation_result = validate_upload_files(pdf_file, excel_file)
        if not validation_result['valid']:
            log_security_event('file_validation_failed', {'errors': validation_result['errors']})
            return secure_error_response('; '.join(validation_result['errors']), 422)
        
        # Generate session ID with more entropy
        import secrets
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        session_id = f"session_{timestamp}_{secrets.token_hex(4)}"
        
        # Create secure filenames
        pdf_secure_name = secure_filename(f"{session_id}_{pdf_file.filename}")
        excel_secure_name = secure_filename(f"{session_id}_{excel_file.filename}")
        
        pdf_path = os.path.join(UPLOAD_FOLDER, pdf_secure_name)
        excel_path = os.path.join(UPLOAD_FOLDER, excel_secure_name)
        
        # Save files securely
        pdf_file.save(pdf_path)
        excel_file.save(excel_path)
        
        # Set restrictive permissions
        os.chmod(pdf_path, 0o600)
        os.chmod(excel_path, 0o600)
        
        # Create processor (quick operation)
        processor = WebStatementProcessor(pdf_path, excel_path, session_id)
        
        # Store session securely so we can track progress
        if not secure_session_manager.create_session(session_id, processor):
            raise ValueError("Failed to create secure session")
        
        # Start background statement extraction
        processor.start_background_extraction()
        
        # Return immediately and redirect to processing page
        return jsonify({
            'status': 'processing',
            'session_id': session_id,
            'redirect_url': url_for('monthly_statements.processing_status', session_id=session_id)
        })
    
    except Exception as e:
        # Clean up files on error
        pdf_path = locals().get('pdf_path')
        excel_path = locals().get('excel_path')
        
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
        if excel_path and os.path.exists(excel_path):
            os.remove(excel_path)
        
        log_security_event('file_processing_error', {'error': str(e)})
        return secure_error_response(f'Processing failed', 500)

@monthly_statements_bp.route('/questions/<session_id>')
@require_valid_session
def questions_page(session_id):
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        log_security_event('invalid_session_access', {'session_id': session_id, 'endpoint': 'questions_page'})
        return render_template('monthly_statements/error.html', error='Session not found'), 404
    
    question_state = processor.get_current_question_state()
    
    return render_template('monthly_statements/questions.html', 
                         session_id=session_id, 
                         question_state=question_state)

@monthly_statements_bp.route('/questions/<session_id>/answer', methods=['POST'])
@require_valid_session
def answer_question(session_id):
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        log_security_event('invalid_session_access', {'session_id': session_id, 'endpoint': 'answer_question'})
        return secure_error_response('Session not found', 404)
    
    response = sanitize_input(request.form.get('response', ''))
    if response not in ['y', 'n', 's', 'p']:
        log_security_event('invalid_response', {'session_id': session_id, 'response': response})
        return secure_error_response('Invalid response', 422)
    
    result = processor.process_question_response(response)
    
    if result.get("completed"):
        # Start background PDF processing
        processor._processing_status = 'processing'
        processor._start_time = datetime.now()
        
        import threading
        def background_pdf_creation():
            try:
                processor._processing_status = 'creating_pdfs'
                results = processor.create_results()
                processor._results = results
                processor._processing_status = 'completed'
            except Exception as e:
                processor._processing_status = 'error'
                processor._error_message = str(e)
        
        thread = threading.Thread(target=background_pdf_creation)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'processing',
            'redirect_url': url_for('monthly_statements.processing_status', session_id=session_id)
        })
    else:
        return jsonify({
            'status': 'continue',
            'question_state': result
        })

@monthly_statements_bp.route('/processing/<session_id>')
@require_valid_session
def processing_status(session_id):
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        log_security_event('invalid_session_access', {'session_id': session_id, 'endpoint': 'processing_status'})
        return render_template('monthly_statements/error.html', error='Session not found'), 404
    
    return render_template('monthly_statements/processing.html', session_id=session_id)

@monthly_statements_bp.route('/processing/<session_id>/status', methods=['GET'])
@require_valid_session
def get_processing_status(session_id):
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        return jsonify({'status': 'error', 'message': 'Session not found'}), 404
    
    status = getattr(processor, '_processing_status', 'unknown')
    pdf_status = getattr(processor, '_pdf_creation_status', 'unknown')
    start_time = getattr(processor, '_start_time', None)
    
    response = {'status': status, 'pdf_status': pdf_status}
    
    if start_time:
        elapsed = (datetime.now() - start_time).total_seconds()
        response['elapsed'] = int(elapsed)
    
    # Check PDF creation timing if available
    pdf_start = getattr(processor, '_pdf_start_time', None)
    pdf_end = getattr(processor, '_pdf_end_time', None)
    if pdf_start:
        import time
        pdf_elapsed = (pdf_end or time.time()) - pdf_start
        response['pdf_elapsed'] = int(pdf_elapsed)
    
    # Handle different completion scenarios
    if status == 'completed' and pdf_status in ['unknown', 'starting']:
        # Initial extraction completed, check for questions
        questions = getattr(processor, 'questions_needed', [])
        if questions:
            response['redirect_url'] = url_for('monthly_statements.questions_page', session_id=session_id)
        else:
            response['redirect_url'] = url_for('monthly_statements.results_page', session_id=session_id)
    elif status == 'completed' and pdf_status == 'completed':
        # Both extraction and PDF creation completed
        response['redirect_url'] = url_for('monthly_statements.results_page', session_id=session_id)
    elif status == 'error':
        response['error'] = getattr(processor, '_error_message', 'Unknown error')
    elif pdf_status == 'error':
        response['error'] = getattr(processor, '_pdf_error', 'PDF creation failed')
    
    return jsonify(response)

@monthly_statements_bp.route('/processing/<session_id>/logs', methods=['GET'])
@require_valid_session
def get_processing_logs(session_id):
    """Get real-time processing logs for debugging"""
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        return jsonify({'error': 'Session not found'}), 404
    
    logs = getattr(processor, '_processing_logs', [])
    return jsonify({
        'logs': logs,
        'count': len(logs),
        'session_id': session_id
    })

@monthly_statements_bp.route('/results/<session_id>')
@require_valid_session
def results_page(session_id):
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        log_security_event('invalid_session_access', {'session_id': session_id, 'endpoint': 'results_page'})
        return render_template('monthly_statements/error.html', error='Session not found'), 404
    if not hasattr(processor, '_results'):
        processor._results = processor.create_results()
    
    # Get the results and update with async PDF files if ready
    results = processor._results.copy()
    if hasattr(processor, '_pdf_files') and processor._pdf_files:
        results['pdf_files'] = processor._pdf_files
        results['pdf_status'] = 'completed'
    
    return render_template('monthly_statements/results.html', 
                         session_id=session_id, 
                         results=results)

@monthly_statements_bp.route('/download/<session_id>')
@require_valid_session
def download_results(session_id):
    processor = secure_session_manager.get_session(session_id)
    if not processor:
        log_security_event('invalid_session_access', {'session_id': session_id, 'endpoint': 'download_results'})
        return secure_error_response('Session not found', 404)
    if not hasattr(processor, '_results'):
        return jsonify({'error': 'Results not found'}), 404
    
    # Create temporary zip file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for dest, file_info in processor._results["pdf_files"].items():
                file_path = file_info["file"]
                if os.path.exists(file_path):
                    zip_file.write(file_path, os.path.basename(file_path))
        
        return send_from_directory(
            os.path.dirname(temp_zip.name),
            os.path.basename(temp_zip.name),
            as_attachment=True,
            download_name=f"monthly_statements_{session_id}.zip"
        )