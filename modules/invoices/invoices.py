from flask import Blueprint, request, redirect, url_for, render_template, send_from_directory, jsonify
import fitz  # PyMuPDF
import re
import os
import logging
from werkzeug.utils import secure_filename
import zipfile
import shutil

# Import security utilities
from security import (
    validate_upload_files,
    sanitize_input,
    secure_error_response,
    log_security_event,
    SecurityConfig
)

invoices_bp = Blueprint('invoices', __name__)

# Configuration
UPLOAD_FOLDER = os.path.abspath('uploads')
RESULT_FOLDER = os.path.abspath('separate_results')
ALLOWED_EXTENSIONS = {'pdf'}

# Setting up logging
logging.basicConfig(level=logging.INFO)

@invoices_bp.route('/clear_results', methods=['POST'])
def clear_results():
    try:
        result_folder = os.path.abspath('separate_results')
        logging.info(f"Attempting to clear contents of {result_folder}")
        
        # Security check: ensure folder exists and is safe to clear
        if not os.path.exists(result_folder):
            return jsonify({'status': 'success', 'message': 'Folder does not exist'})
        
        if os.path.exists(result_folder):
            for file in os.listdir(result_folder):
                file_path = os.path.join(result_folder, file)
                
                # Security check: ensure path is within result folder
                if not os.path.abspath(file_path).startswith(os.path.abspath(result_folder)):
                    log_security_event('path_traversal_attempt_clear', {'file_path': file_path})
                    continue
                
                if os.path.isfile(file_path):
                    logging.info(f"Deleting file: {file_path}")
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    logging.info(f"Deleting directory and its contents: {file_path}")
                    shutil.rmtree(file_path)
        
        logging.info("Finished clearing results folder.")
        return jsonify({'status': 'success'})
    
    except Exception as e:
        log_security_event('clear_results_error', {'error': str(e)})
        return secure_error_response('Clear operation failed', 500)

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def extract_invoice_numbers_and_split(input_pdf, output_folder):
    doc = fitz.open(input_pdf)
    pattern = r'\b[P|R]\d{6,8}\b'  # Modified regex to match 6, 7, or 8 digits
    invoices_found = False
    try:
        pages_by_invoice = {}
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            invoice_numbers = re.findall(pattern, text)
            if invoice_numbers:
                invoices_found = True
            for invoice_number in invoice_numbers:
                if invoice_number not in pages_by_invoice:
                    pages_by_invoice[invoice_number] = []
                pages_by_invoice[invoice_number].append(page_num)

        if not invoices_found:
            return False  # No invoices found

        for invoice_number, page_nums in pages_by_invoice.items():
            output_pdf = fitz.open()
            for page_num in page_nums:
                output_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
            output_filename = os.path.join(output_folder, f"{invoice_number}.pdf")
            output_pdf.save(output_filename)
            output_pdf.close()
    finally:
        doc.close()
    return True

@invoices_bp.route('/')
def upload_file():
    return render_template('invoices/upload.html')

@invoices_bp.route('/process', methods=['POST'])
def process_file():
    try:
        logging.info("Received a request to process file.")
        
        # Check if file is present
        if 'file' not in request.files:
            log_security_event('missing_file', {'missing': 'file'})
            return secure_error_response('No file provided', 400)
        
        pdf_file = request.files['file']
        
        # Validate PDF file directly
        from security import validate_filename, validate_file_content, SecurityConfig
        
        if not pdf_file.filename:
            log_security_event('missing_filename', {'file_type': 'PDF'})
            return secure_error_response('No filename provided', 400)
        
        # Validate filename
        if not validate_filename(pdf_file.filename):
            log_security_event('invalid_filename', {'filename': pdf_file.filename})
            return secure_error_response('Invalid filename', 422)
        
        # Validate file content
        pdf_validation = validate_file_content(pdf_file, SecurityConfig.ALLOWED_EXTENSIONS['pdf'])
        if not pdf_validation['valid']:
            log_security_event('file_validation_failed', {'error': pdf_validation['error']})
            return secure_error_response(pdf_validation['error'], 422)
        
        if pdf_file and pdf_file.filename.lower().endswith('.pdf'):
            logging.info(f"File {pdf_file.filename} is allowed and will be processed.")
            
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
                logging.info(f"Created upload folder: {UPLOAD_FOLDER}")
            
            filename = secure_filename(pdf_file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            pdf_file.save(file_path)
            
            # Set restrictive permissions
            os.chmod(file_path, 0o600)
            logging.info(f"Saved file to {file_path}")
        
            if not os.path.exists(RESULT_FOLDER):
                os.makedirs(RESULT_FOLDER)
                logging.info(f"Created result folder: {RESULT_FOLDER}")
            
            result_folder = os.path.join(RESULT_FOLDER, filename.rsplit('.', 1)[0], 'separateInvoices')
            os.makedirs(result_folder, exist_ok=True)
            logging.info(f"Created result subfolder: {result_folder}")
            
            invoices_found = extract_invoice_numbers_and_split(file_path, result_folder)
            logging.info(f"Invoices found: {invoices_found}")
            
            if not invoices_found:
                message = 'The PDF you chose does not contain any invoice'
                logging.info(message)
                return jsonify({'error': message}), 400
            else:
                zip_filename = f"{filename.rsplit('.', 1)[0]}.zip"
                zip_path = os.path.join(RESULT_FOLDER, zip_filename)
                
                if not os.path.isfile(zip_path):
                    logging.info(f"Creating zip file: {zip_filename}")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for root, dirs, files in os.walk(result_folder):
                            for file in files:
                                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), result_folder))
                    logging.info(f"Created zip file at {zip_path}")
                
                message = 'Invoices separated successfully. Find PDF files in your downloads.'
                logging.info(message)
                return jsonify({
                    'success': True,
                    'message': message,
                    'zip_filename': zip_filename,
                    'download_url': url_for('invoices.download_file', filename=zip_filename)
                })
        else:
            logging.info("File is not allowed or not a PDF.")
            return jsonify({'error': 'The file is not a valid PDF or is not allowed.'}), 400
    
    except Exception as e:
        # Clean up files on error
        file_path = locals().get('file_path')
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        log_security_event('file_processing_error', {'error': str(e)})
        return secure_error_response('Processing failed', 500)

@invoices_bp.route('/downloads/<filename>')
def download_file(filename):
    # Import security functions
    from security import validate_filename
    
    # Validate filename for security
    if not validate_filename(filename):
        log_security_event('invalid_download_filename', {'filename': filename})
        return secure_error_response('Invalid filename', 422)
    
    # Use secure_filename to prevent path traversal
    secure_name = secure_filename(filename)
    zip_path = os.path.join(RESULT_FOLDER, secure_name)
    
    # Ensure path is within RESULT_FOLDER (prevent directory traversal)
    if not os.path.abspath(zip_path).startswith(os.path.abspath(RESULT_FOLDER)):
        log_security_event('path_traversal_attempt', {'requested_path': filename})
        return secure_error_response('Access denied', 403)
    
    if os.path.exists(zip_path):
        return send_from_directory(RESULT_FOLDER, secure_name, as_attachment=True)
    else:
        log_security_event('file_not_found', {'filename': secure_name})
        return secure_error_response('File not found', 404)

@invoices_bp.route('/delete_separate_results', methods=['POST'])
def delete_separate_results():
    try:
        # Security check: validate the folder path
        if not os.path.abspath(RESULT_FOLDER).startswith(os.getcwd()):
            log_security_event('invalid_folder_path', {'folder': RESULT_FOLDER})
            return secure_error_response('Invalid folder path', 403)
        
        if os.path.exists(RESULT_FOLDER):
            shutil.rmtree(RESULT_FOLDER)
            logging.info(f"Deleted contents of {RESULT_FOLDER}")
            os.makedirs(RESULT_FOLDER)
            logging.info(f"Recreated empty result folder: {RESULT_FOLDER}")
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        log_security_event('delete_results_error', {'error': str(e)})
        return secure_error_response('Delete operation failed', 500)