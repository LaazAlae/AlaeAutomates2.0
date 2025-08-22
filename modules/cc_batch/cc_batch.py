from flask import Blueprint, render_template, request, jsonify
import openpyxl
import json
import logging
import os
import re
from werkzeug.utils import secure_filename
import tempfile

credit_card_batch_bp = Blueprint('credit_card_batch', __name__)
cc_batch_bp = credit_card_batch_bp  # Alias for backward compatibility

# Configuration
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@cc_batch_bp.route('/')
def cc_batch():
    return render_template('cc_batch/generator.html')

@cc_batch_bp.route('/process', methods=['POST'])
def process_credit_card_batch():
    """Process Excel file and generate credit card batch automation code"""
    logging.info("Credit card batch processing request received")
    
    try:
        # Check if file is uploaded (support both 'file' and 'excel_file' keys)
        file = None
        if 'file' in request.files:
            file = request.files['file']
        elif 'excel_file' in request.files:
            file = request.files['excel_file']
        
        if not file:
            return jsonify({
                'success': False,
                'error': 'No file uploaded'
            }), 400
            
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': 'Invalid file type. Please upload Excel file (.xlsx or .xls)'
            }), 400
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            file.save(tmp_file.name)
            temp_path = tmp_file.name
        
        try:
            # Process the Excel file
            processed_data = process_excel_file(temp_path)
            
            if not processed_data:
                return jsonify({
                    'success': False,
                    'error': 'No valid data found in Excel file'
                }), 400
            
            # Generate improved JavaScript automation code
            automation_code = generate_improved_automation_code(processed_data)
            
            return jsonify({
                'success': True,
                'message': f'Successfully processed {len(processed_data)} records',
                'records_count': len(processed_data),
                'processed_data': processed_data[:5],  # Show first 5 records for preview
                'javascript_code': automation_code
            })
        
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    
    except Exception as e:
        logging.error(f"Credit card batch processing error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Processing failed: {str(e)}'
        }), 500

@credit_card_batch_bp.route('/download-code', methods=['POST'])
def download_code():
    """Download generated JavaScript code as .js file"""
    try:
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'error': 'No code provided'}), 400
        
        code = data['code']
        
        # Create response with JavaScript file
        from flask import make_response
        response = make_response(code)
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Content-Disposition'] = 'attachment; filename=cc_batch_automation.js'
        
        return response
        
    except Exception as e:
        logging.error(f"Code download error: {str(e)}")
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

def process_excel_file(file_path):
    """Process Excel file - implement the macro functionality using correct column mapping"""
    try:
        # Read Excel file using openpyxl
        workbook = openpyxl.load_workbook(file_path)
        worksheet = workbook.active
        
        # The Excel file structure based on VBA macro:
        # Column A: (deleted in macro) - skip
        # Column B: Invoice Number 
        # Column C: (deleted in macro) - skip  
        # Column D: (deleted in macro) - skip
        # Column E: Customer Name (lastname, firstname format)
        # Column F: Card Type (A/V/M/D)
        # Column G: Card Number with XXXX prefix
        # Column H: Settlement Amount
        
        cleaned_data = []
        
        for row_index, row in enumerate(worksheet.iter_rows(values_only=True), 1):
            try:
                # Skip empty rows
                if not any(cell for cell in row if cell is not None):
                    continue
                
                # Extract data from correct columns (0-indexed)
                invoice_number = str(row[1]) if len(row) > 1 and row[1] is not None else ""  # Column B
                customer = str(row[4]) if len(row) > 4 and row[4] is not None else ""         # Column E  
                card_type = str(row[5]) if len(row) > 5 and row[5] is not None else ""        # Column F
                card_number = str(row[6]) if len(row) > 6 and row[6] is not None else ""      # Column G
                settlement = str(row[7]) if len(row) > 7 and row[7] is not None else ""       # Column H
                
                # Skip if any critical field is missing or invalid
                if not settlement or settlement == 'nan':
                    continue
                    
                # Skip if settlement amount is in parentheses (refund)
                if '(' in settlement and ')' in settlement:
                    continue
                
                # Process customer name (lastname, firstname -> firstname lastname)
                if ',' in customer:
                    parts = customer.split(',', 1)  # Split only on first comma
                    if len(parts) >= 2:
                        last_name = parts[0].strip()
                        first_name = parts[1].strip()
                        customer = f"{first_name} {last_name}"
                
                # Special case for BILL.COM
                if 'BILL .COM' in customer.upper():
                    customer = 'BILL.COM'
                
                # Process card payment method - combine card type and last 4 digits
                payment_method = ""
                if card_type and card_number:
                    # Map card type letters to full names
                    if card_type.upper().startswith('A'):
                        payment_method = "AMEX-"
                    elif card_type.upper().startswith('V'):
                        payment_method = "VISA-"
                    elif card_type.upper().startswith('M'):
                        payment_method = "MC-"
                    elif card_type.upper().startswith('D'):
                        payment_method = "DISC-"
                    
                    # Extract last 4 digits, remove XXXX prefix
                    if 'XXXX' in card_number:
                        card_digits = card_number.replace('XXXX', '').strip()
                        # Ensure it's 4 digits
                        if card_digits.isdigit():
                            card_last_four = card_digits.zfill(4)
                            payment_method += card_last_four
                    elif card_number.isdigit():
                        # If it's just numbers, take last 4
                        card_last_four = card_number[-4:].zfill(4)
                        payment_method += card_last_four
                
                # Process invoice number
                processed_invoice = ""
                if invoice_number and invoice_number != 'nan':
                    # Clean multiple invoice numbers (take only first)
                    if ',' in invoice_number:
                        invoice_number = invoice_number.split(',')[0].strip()
                    
                    # Clean whitespace and convert to uppercase
                    invoice_number = invoice_number.strip().upper()
                    
                    # Validate invoice format (P or R followed by digits)
                    if re.match(r'^[PR]\d+', invoice_number):
                        processed_invoice = invoice_number
                    else:
                        # Invalid invoice format - use line number for manual review
                        processed_invoice = f"Line {row_index} TBD manually"
                else:
                    processed_invoice = f"Line {row_index} TBD manually"
                
                # Clean settlement amount
                try:
                    # Remove currency symbols, commas, and whitespace
                    clean_amount_str = re.sub(r'[^\d.-]', '', str(settlement))
                    settlement_amount = float(clean_amount_str)
                    settlement_formatted = f"{settlement_amount:.2f}"
                except:
                    settlement_formatted = "0.00"
                
                # Skip zero amounts
                if float(settlement_formatted) == 0:
                    continue
                
                cleaned_data.append({
                    'invoice': processed_invoice,
                    'payment_method': payment_method,
                    'amount': settlement_formatted,
                    'customer': customer.strip()
                })
                
            except Exception as e:
                # Log error but continue processing
                logging.error(f"Error processing row {row_index}: {str(e)}")
                continue
        
        workbook.close()
        logging.info(f"Processed {len(cleaned_data)} valid records from Excel")
        return cleaned_data
    
    except Exception as e:
        logging.error(f"Excel processing error: {str(e)}")
        raise


def generate_improved_automation_code(records_data):
    """Generate clean, safe JavaScript automation code based on working version"""
    
    # Convert records to proper format for the working version
    formatted_data = []
    for record in records_data:
        formatted_data.append({
            'invoiceNumber': record['invoice'],
            'cardPaymentMethod': record['payment_method'], 
            'settlementAmount': record['amount'],
            'customer': record['customer']
        })
    
    json_data = json.dumps(formatted_data, indent=2)
    
    # Generate clean automation code based on your working version
    code = f'''// SIMPLIFIED HEADLESS PAYMENT AUTOMATION
// Generated for {len(records_data)} payment records
// Just type run() on each page!

// PAYMENT DATA
var PAYMENT_DATA = {json_data};

// PAGE DETECTION
function detectPageAndStep() {{
    var url = window.location.href.toLowerCase();
    var bodyText = document.body.textContent || document.body.innerText || '';
    
    if (url.indexOf('receipt_add_invoice.aspx') !== -1) {{
        var amountField = document.getElementsByName('ctl00$ContentPlaceHolder1$txtAmount')[0];
        var customerField = document.getElementsByName('ctl00$ContentPlaceHolder1$txtCheckName')[0];
        var paymentNumberField = document.getElementsByName('ctl00$ContentPlaceHolder1$txtNumber')[0];
        
        if (customerField && customerField.value && customerField.value.trim() !== '') {{
            return {{ page: 'PAYMENT_FORM_PAGE', step: 8 }};
        }} else if (amountField && amountField.value && amountField.value.trim() !== '') {{
            return {{ page: 'PAYMENT_FORM_PAGE', step: 7 }};
        }} else if (paymentNumberField && paymentNumberField.value && paymentNumberField.value.trim() !== '') {{
            return {{ page: 'PAYMENT_FORM_PAGE', step: 6 }};
        }} else {{
            return {{ page: 'PAYMENT_FORM_PAGE', step: 4 }};
        }}
    }} else if (url.indexOf('batch_page.aspx') !== -1) {{
        if (url.indexOf('view=recadd') !== -1) {{
            return {{ page: 'ADD_RECEIPT_PAGE', step: 1 }};
        }} else if (url.indexOf('view=isrch') !== -1) {{
            var invoiceField = document.getElementsByName('ctl00$ContentPlaceHolder1$txtNumber')[0];
            if (invoiceField && invoiceField.value && invoiceField.value.trim() !== '') {{
                return {{ page: 'SEARCH_PAGE', step: 3 }};
            }} else {{
                return {{ page: 'SEARCH_PAGE', step: 2 }};
            }}
        }} else {{
            if (bodyText.indexOf('Add Receipt') !== -1) {{
                return {{ page: 'MAIN_BATCH_PAGE', step: 0 }};
            }}
        }}
    }}
    return {{ page: 'UNKNOWN_PAGE', step: 0 }};
}}

// SAFETY HELPERS WITH IMPROVED RELIABILITY
function isElementVisible(element) {{
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return (
        rect.width > 0 &&
        rect.height > 0 &&
        style.visibility !== 'hidden' &&
        style.display !== 'none' &&
        element.offsetParent !== null
    );
}}

function safeClick(element) {{
    if (element && isElementVisible(element) && !element.disabled) {{
        element.focus();
        element.click();
        return true;
    }}
    return false;
}}

function safeFillField(element, value) {{
    if (element && isElementVisible(element) && !element.disabled) {{
        element.focus();
        element.value = value;
        
        // Trigger events for both legacy and modern browsers
        if (element.onchange) element.onchange();
        if (element.oninput) element.oninput();
        
        try {{
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
            element.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }} catch (e) {{
            // Fallback for older browsers
        }}
        return true;
    }}
    return false;
}}

// ENHANCED AUTOMATION
function HeadlessAutomation() {{
    var pageInfo = detectPageAndStep();
    this.currentPageState = pageInfo.page;
    this.processingStep = pageInfo.step;
    
    var cookieIndex = this.getCookie('automationIndex');
    if (cookieIndex !== null) {{
        this.currentRecordIndex = parseInt(cookieIndex);
    }} else {{
        this.currentRecordIndex = 0;
    }}
    
    this.currentRecord = PAYMENT_DATA[this.currentRecordIndex];
    
    console.log('=======================================');
    console.log('AUTOMATION STATUS');
    console.log('=======================================');
    console.log('Page: ' + this.currentPageState);
    console.log('Record: ' + (this.currentRecordIndex + 1) + '/' + PAYMENT_DATA.length);
    if (this.currentRecord) {{
        console.log('Processing: ' + this.currentRecord.invoiceNumber + ' - ' + this.currentRecord.customer);
        console.log('Amount: ' + this.currentRecord.settlementAmount);
        console.log('Method: ' + this.currentRecord.cardPaymentMethod);
    }}
    console.log('Step: ' + this.getStepName(this.processingStep));
    console.log('=======================================');
}}

HeadlessAutomation.prototype.getStepName = function(step) {{
    var stepNames = [
        'Click Add Receipt',
        'Click By Invoice', 
        'Enter Invoice Number',
        'Click Search',
        'Select Payment Type',
        'Enter Payment Method',
        'Enter Amount',
        'Enter Customer Name',
        'Click Save',
        'Complete'
    ];
    return stepNames[step] || 'Unknown';
}};

HeadlessAutomation.prototype.execute = function() {{
    if (!this.currentRecord) {{
        console.log('ALL RECORDS COMPLETED!');
        return;
    }}
    
    var self = this;
    
    switch (this.processingStep) {{
        case 0: // Click Add Receipt
            console.log('Clicking "Add Receipt"...');
            this.clickButton('Add Receipt');
            console.log('Done! Page will redirect...');
            break;
            
        case 1: // Click By Invoice
            console.log('Clicking "By Invoice"...');
            this.clickButton('By Invoice');
            console.log('Done! Page will redirect...');
            break;
            
        case 2: // Enter Invoice Number
            var cleanInvoice = this.cleanInvoiceNumber(this.currentRecord.invoiceNumber);
            console.log('Entering invoice: ' + cleanInvoice);
            this.fillFieldSafe('ctl00$ContentPlaceHolder1$txtNumber', cleanInvoice);
            console.log('Invoice entered!');
            setTimeout(function() {{
                console.log('Clicking "Search"...');
                self.clickButton('Search');
                console.log('Search clicked! Page will redirect...');
            }}, 1000);
            break;
            
        case 3: // Click Search (if invoice already entered)
            console.log('Clicking "Search"...');
            this.clickButton('Search');
            console.log('Done! Page will redirect to payment form...');
            break;
            
        case 4: // Payment form - start filling
            console.log('Starting payment form fill...');
            var paymentType = this.determinePaymentType(this.currentRecord.cardPaymentMethod);
            console.log('Selecting payment type: ' + paymentType);
            this.selectDropdown('ctl00$ContentPlaceHolder1$lstType', paymentType);
            
            setTimeout(function() {{
                console.log('Entering payment method: ' + self.currentRecord.cardPaymentMethod);
                self.fillFieldSafe('ctl00$ContentPlaceHolder1$txtNumber', self.currentRecord.cardPaymentMethod);
                
                setTimeout(function() {{
                    console.log('Entering amount: ' + self.currentRecord.settlementAmount);
                    self.fillFieldSafe('ctl00$ContentPlaceHolder1$txtAmount', self.currentRecord.settlementAmount);
                    
                    setTimeout(function() {{
                        console.log('Entering customer: ' + self.currentRecord.customer);
                        self.fillFieldSafe('ctl00$ContentPlaceHolder1$txtCheckName', self.currentRecord.customer);
                        
                        setTimeout(function() {{
                            console.log('Clicking "Save"...');
                            self.clickButton('Save');
                            console.log('Payment saved!');
                            
                            self.nextRecord();
                            console.log('Ready for next record. Navigate to main batch page and run again.');
                        }}, 1000);
                    }}, 500);
                }}, 500);
            }}, 500);
            break;
            
        case 5: // If payment method already selected
        case 6: // If amount already entered
        case 7: // If customer already entered
            console.log('Form partially filled, completing remaining fields...');
            setTimeout(function() {{ self.completeForm(); }}, 500);
            break;
            
        case 8: // Ready to save
            console.log('Clicking "Save"...');
            this.clickButton('Save');
            console.log('Payment saved!');
            this.nextRecord();
            console.log('Ready for next record. Navigate to main batch page and run again.');
            break;
            
        default:
            console.log('Unknown step: ' + this.processingStep);
    }}
}};

HeadlessAutomation.prototype.completeForm = function() {{
    var self = this;
    var amountField = document.getElementsByName('ctl00$ContentPlaceHolder1$txtAmount')[0];
    var customerField = document.getElementsByName('ctl00$ContentPlaceHolder1$txtCheckName')[0];
    
    if (!amountField.value) {{
        console.log('Entering amount: ' + this.currentRecord.settlementAmount);
        this.fillFieldSafe('ctl00$ContentPlaceHolder1$txtAmount', this.currentRecord.settlementAmount);
    }}
    
    setTimeout(function() {{
        if (!customerField.value) {{
            console.log('Entering customer: ' + self.currentRecord.customer);
            self.fillFieldSafe('ctl00$ContentPlaceHolder1$txtCheckName', self.currentRecord.customer);
        }}
        
        setTimeout(function() {{
            console.log('Clicking "Save"...');
            self.clickButton('Save');
            console.log('Payment saved!');
            self.nextRecord();
        }}, 1000);
    }}, 500);
}};

HeadlessAutomation.prototype.nextRecord = function() {{
    this.currentRecordIndex++;
    this.setCookie('automationIndex', this.currentRecordIndex.toString());
    
    if (this.currentRecordIndex < PAYMENT_DATA.length) {{
        this.currentRecord = PAYMENT_DATA[this.currentRecordIndex];
        console.log('');
        console.log('Next record: ' + this.currentRecord.invoiceNumber);
    }} else {{
        this.currentRecord = null;
        console.log('');
        console.log('ALL RECORDS COMPLETED!');
    }}
}};

// UTILITY FUNCTIONS WITH ENHANCED SAFETY
HeadlessAutomation.prototype.clickButton = function(buttonText) {{
    var buttons = document.getElementsByTagName('input');
    for (var i = 0; i < buttons.length; i++) {{
        if (buttons[i].value === buttonText && 
            (buttons[i].type === 'submit' || buttons[i].type === 'button') &&
            isElementVisible(buttons[i]) && !buttons[i].disabled) {{
            return safeClick(buttons[i]);
        }}
    }}
    console.log('Button "' + buttonText + '" not found');
    return false;
}};

HeadlessAutomation.prototype.fillFieldSafe = function(fieldName, value) {{
    var field = document.getElementsByName(fieldName)[0];
    if (field && isElementVisible(field) && !field.disabled) {{
        return safeFillField(field, value);
    }}
    console.log('Field "' + fieldName + '" not found or not accessible');
    return false;
}};

HeadlessAutomation.prototype.selectDropdown = function(dropdownName, value) {{
    var dropdown = document.getElementsByName(dropdownName)[0];
    if (dropdown && isElementVisible(dropdown) && !dropdown.disabled) {{
        for (var i = 0; i < dropdown.options.length; i++) {{
            if (dropdown.options[i].text.indexOf(value) !== -1) {{
                dropdown.selectedIndex = i;
                dropdown.value = dropdown.options[i].value;
                if (dropdown.onchange) dropdown.onchange();
                try {{
                    dropdown.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }} catch (e) {{
                    // Fallback for older browsers
                }}
                return true;
            }}
        }}
    }}
    console.log('Dropdown "' + dropdownName + '" or option "' + value + '" not found');
    return false;
}};

HeadlessAutomation.prototype.cleanInvoiceNumber = function(invoice) {{
    return invoice.replace(/^[RP]/i, '');
}};

HeadlessAutomation.prototype.determinePaymentType = function(method) {{
    var methodUpper = method.toUpperCase();
    if (methodUpper.indexOf('AMEX') !== -1) return 'AMEX';
    if (methodUpper.indexOf('VISA') !== -1) return 'VISA';
    if (methodUpper.indexOf('MC') !== -1) return 'MasterCard';
    if (methodUpper.indexOf('DISC') !== -1) return 'Discover';
    return 'Check';
}};

HeadlessAutomation.prototype.setCookie = function(name, value) {{
    document.cookie = name + '=' + value + '; path=/';
}};

HeadlessAutomation.prototype.getCookie = function(name) {{
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {{
        var cookie = cookies[i].trim();
        if (cookie.indexOf(name + '=') === 0) {{
            return cookie.substring(name.length + 1);
        }}
    }}
    return null;
}};

// INITIALIZE AND EXECUTE IMMEDIATELY
var auto = new HeadlessAutomation();
auto.execute();

// Create run function for easy re-execution
window.run = function() {{
    auto = new HeadlessAutomation();
    auto.execute();
}};

// Reset function if needed
window.reset = function() {{
    document.cookie = 'automationIndex=0; path=/';
    console.log('Reset to first record');
}};

console.log('');
console.log('TIP: Type run() to execute | reset() to start over');
console.log('SIMPLIFIED: Always syncs to current page!');'''

    return code