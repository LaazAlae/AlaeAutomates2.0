###############################################################################
# CREDIT CARD BATCH PROCESSING MODULE
# Automated Excel processing and JavaScript code generation for payment systems
###############################################################################

from flask import Blueprint, render_template, request, jsonify, send_file
import pandas as pd
import re
import os
import tempfile
from datetime import datetime
from security import validate_upload_files, sanitize_input, secure_error_response, log_security_event
from werkzeug.utils import secure_filename
from flask_wtf.csrf import validate_csrf
from flask_wtf import FlaskForm

cc_batch_bp = Blueprint('cc_batch', __name__)


###############################################################################
# EXCEL PROCESSING LOGIC
# Server-side implementation of VBA macro functionality
###############################################################################

def process_excel_data(df):
    """Process Excel data according to macro logic - O(n) where n is number of rows"""
    
    # Remove title row if it exists (first row with headers)
    if len(df) > 0 and 'Invoice' in str(df.iloc[0]).upper():
        df = df.iloc[1:].reset_index(drop=True)
    
    processed_data = []
    line_number = 1
    
    for _, row in df.iterrows():
        try:
            # Extract data from expected columns (adjust based on your Excel structure)
            invoice_number = str(row.iloc[1]) if len(row) > 1 else ""  # Column B
            card_payment = str(row.iloc[2]) if len(row) > 2 else ""     # Column C  
            settlement = str(row.iloc[3]) if len(row) > 3 else ""       # Column D
            customer = str(row.iloc[4]) if len(row) > 4 else ""         # Column E
            
            # Skip if settlement amount is in parentheses (refund)
            if '(' in settlement and ')' in settlement:
                line_number += 1
                continue
            
            # Process customer name (lastname, firstname -> firstname lastname)
            if ',' in customer:
                parts = customer.split(',')
                if len(parts) >= 2:
                    last_name = parts[0].strip()
                    first_name = parts[1].strip()
                    customer = f"{first_name} {last_name}"
            
            # Special case for BILL.COM
            if 'BILL .COM' in customer.upper():
                customer = 'BILL.COM'
            
            # Process card payment method
            payment_method = ""
            card_last_four = ""
            
            if card_payment:
                # Extract card type
                if card_payment.startswith('A'):
                    payment_method = "AMEX-"
                elif card_payment.startswith('V'):
                    payment_method = "VISA-"
                elif card_payment.startswith('M'):
                    payment_method = "MC-"
                elif card_payment.startswith('D'):
                    payment_method = "DISC-"
                
                # Extract last 4 digits, remove XXXX prefix
                card_digits = re.search(r'XXXX(\d+)', card_payment)
                if card_digits:
                    card_last_four = card_digits.group(1).zfill(4)
                    payment_method += card_last_four
            
            # Process invoice number
            processed_invoice = ""
            if invoice_number and invoice_number != 'nan':
                # Clean multiple invoice numbers (take only first)
                if ',' in invoice_number:
                    invoice_number = invoice_number.split(',')[0].strip()
                
                # Validate invoice format (P or R followed by digits)
                if re.match(r'^[PR]\d+', invoice_number.upper()):
                    processed_invoice = invoice_number.upper()
                else:
                    # Invalid invoice format - use line number for manual review
                    processed_invoice = f"Line {line_number} TBD manually"
            else:
                processed_invoice = f"Line {line_number} TBD manually"
            
            # Clean settlement amount
            try:
                settlement_amount = float(re.sub(r'[^\d.-]', '', settlement))
                settlement_formatted = f"{settlement_amount:.2f}"
            except:
                settlement_formatted = "0.00"
            
            processed_data.append({
                'invoice': processed_invoice,
                'payment_method': payment_method,
                'amount': settlement_formatted,
                'customer': customer
            })
            
        except Exception as e:
            # Log error but continue processing
            log_security_event('excel_processing_error', {'line': line_number, 'error': str(e)})
        
        line_number += 1
    
    return processed_data


###############################################################################
# JAVASCRIPT CODE GENERATION
# Generate browser console code for automated form filling
###############################################################################

def generate_javascript_code(processed_data):
    """Generate JavaScript automation code - O(n) complexity"""
    
    js_code = """// Credit Card Batch Processing Automation
// Generated by AlaeAutomates 2.0
// Paste this code in browser console (F12) on payment processing page

let batchData = [
"""
    
    for item in processed_data:
        js_code += f"""    {{
        invoice: "{item['invoice']}",
        paymentMethod: "{item['payment_method']}",
        amount: "{item['amount']}",
        customer: "{item['customer']}"
    }},
"""
    
    js_code += """];

let currentIndex = 0;

function run() {
    if (currentIndex >= batchData.length) {
        console.log('Batch processing complete!');
        return;
    }
    
    const data = batchData[currentIndex];
    console.log(`Processing ${currentIndex + 1}/${batchData.length}: ${data.invoice}`);
    
    // Fill form fields (adjust selectors based on your payment system)
    try {
        // Invoice number field
        const invoiceField = document.querySelector('input[name*="invoice"], input[id*="invoice"], input[placeholder*="invoice"]');
        if (invoiceField) invoiceField.value = data.invoice;
        
        // Payment method field
        const paymentField = document.querySelector('input[name*="payment"], input[id*="payment"], select[name*="card"]');
        if (paymentField) paymentField.value = data.paymentMethod;
        
        // Amount field
        const amountField = document.querySelector('input[name*="amount"], input[id*="amount"], input[type="number"]');
        if (amountField) amountField.value = data.amount;
        
        // Customer name field
        const customerField = document.querySelector('input[name*="customer"], input[id*="customer"], input[name*="name"]');
        if (customerField) customerField.value = data.customer;
        
        // Trigger change events
        [invoiceField, paymentField, amountField, customerField].forEach(field => {
            if (field) {
                field.dispatchEvent(new Event('change', { bubbles: true }));
                field.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
        
        console.log('✓ Form filled. Click submit, then call run() again for next entry.');
        currentIndex++;
        
    } catch (error) {
        console.error('Error filling form:', error);
        console.log('Skipping to next entry...');
        currentIndex++;
        run(); // Auto-continue on error
    }
}

console.log(`Loaded ${batchData.length} records. Call run() to start processing.`);
console.log('Usage: run() -> submit form -> run() -> submit form -> repeat');
"""
    
    return js_code


###############################################################################
# ROUTE HANDLERS
# File upload and processing endpoints
###############################################################################

@cc_batch_bp.route('/')
def cc_batch():
    return render_template('cc_batch/generator.html')

@cc_batch_bp.route('/process', methods=['POST'])
def process_batch():
    """Process uploaded Excel file and generate JavaScript code"""
    
    try:
        # Validate CSRF token
        try:
            validate_csrf(request.form.get('csrf_token'))
        except Exception as e:
            log_security_event('csrf_validation_failed', {'endpoint': 'cc_batch_process', 'error': str(e)})
            return secure_error_response('CSRF token validation failed', 400)
        
        # Validate file upload
        if 'excel_file' not in request.files:
            return secure_error_response('No Excel file uploaded', 400)
        
        excel_file = request.files['excel_file']
        if not excel_file.filename:
            return secure_error_response('No file selected', 400)
        
        # Basic file validation
        if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
            return secure_error_response('Please upload an Excel file (.xlsx or .xls)', 400)
        
        # Save uploaded file temporarily
        temp_dir = tempfile.mkdtemp()
        filename = secure_filename(excel_file.filename)
        temp_path = os.path.join(temp_dir, filename)
        excel_file.save(temp_path)
        
        try:
            # Read Excel file
            df = pd.read_excel(temp_path, header=None)
            
            if df.empty:
                return secure_error_response('Excel file is empty', 400)
            
            # Process the data
            processed_data = process_excel_data(df)
            
            if not processed_data:
                return secure_error_response('No valid data found in Excel file', 400)
            
            # Generate JavaScript code
            js_code = generate_javascript_code(processed_data)
            
            # Log successful processing
            log_security_event('cc_batch_processed', {
                'filename': filename,
                'records_processed': len(processed_data)
            })
            
            return jsonify({
                'success': True,
                'records_count': len(processed_data),
                'javascript_code': js_code,
                'processed_data': processed_data[:5]  # Preview of first 5 records
            })
            
        except Exception as e:
            log_security_event('cc_batch_error', {'filename': filename, 'error': str(e)})
            return secure_error_response(f'Error processing Excel file: {str(e)}', 500)
        
        finally:
            # Cleanup temporary file
            try:
                os.remove(temp_path)
                os.rmdir(temp_dir)
            except:
                pass
    
    except Exception as e:
        return secure_error_response('File processing failed', 500)

@cc_batch_bp.route('/download-code', methods=['POST'])
def download_code():
    """Download generated JavaScript code as a file"""
    
    try:
        # Validate CSRF token
        try:
            csrf_token = request.headers.get('X-CSRFToken') or request.json.get('csrf_token')
            validate_csrf(csrf_token)
        except Exception as e:
            log_security_event('csrf_validation_failed', {'endpoint': 'cc_batch_download', 'error': str(e)})
            return secure_error_response('CSRF token validation failed', 400)
        
        js_code = request.json.get('code', '')
        if not js_code:
            return secure_error_response('No code provided', 400)
        
        # Create temporary file
        temp_dir = tempfile.mkdtemp()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cc_batch_automation_{timestamp}.js"
        temp_path = os.path.join(temp_dir, filename)
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(js_code)
        
        return send_file(temp_path, as_attachment=True, download_name=filename, mimetype='application/javascript')
    
    except Exception as e:
        return secure_error_response('Code download failed', 500)