"""
Web Application for Web Stryker R7 Python Edition
Provides a web interface for extraction functionality
"""
import os
import time
import threading
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename

# Import application modules
from domain_models import ExtractionState, global_stats
from config import config
from logging_system import log_repository
from extraction_service import extraction_service
from data_repository import data_repository


# Initialize Flask app
app = Flask(__name__, 
            static_folder="static",
            template_folder="templates")

# Configure app
app.config['SECRET_KEY'] = config.get("WEB_UI.SECRET_KEY", "change-this-in-production")
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def run_async_task(coroutine, callback=None):
    """Run an async task from synchronous code"""
    
    def _run_in_thread(coro, loop, callback):
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        if callback:
            callback(result)
    
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=_run_in_thread, args=(coroutine, loop, callback))
    thread.daemon = True
    thread.start()
    return thread


@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/extract', methods=['GET', 'POST'])
def extract():
    """Extraction page"""
    if request.method == 'POST':
        # Handle URL submission
        url = request.form.get('url')
        if not url:
            return render_template('extract.html', error="Please enter a URL")
        
        # Check if URL starts with http:// or https://
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Generate extraction ID
        extraction_id = f"web-{int(time.time())}"
        
        # Start extraction in background
        run_async_task(extraction_service.process_url(url, extraction_id))
        
        # Redirect to extraction status page
        return redirect(url_for('extraction_status', extraction_id=extraction_id, url=url))
    
    # GET request
    return render_template('extract.html')


@app.route('/extraction-status/<extraction_id>')
def extraction_status(extraction_id):
    """Show extraction status"""
    url = request.args.get('url', 'unknown')
    return render_template('extraction_status.html', extraction_id=extraction_id, url=url)


@app.route('/api/extraction-progress/<extraction_id>')
def api_extraction_progress(extraction_id):
    """API endpoint for getting extraction progress"""
    state = ExtractionState.get_state(extraction_id)
    
    if not state:
        return jsonify({
            'found': False,
            'progress': 0,
            'stage': 'Not found'
        })
    
    return jsonify({
        'found': True,
        'progress': state['progress'],
        'stage': state['stage'],
        'paused': state['paused'],
        'stopped': state['stopped'],
        'url': state.get('url', 'Unknown')
    })


@app.route('/api/extraction-result/<extraction_id>')
def api_extraction_result(extraction_id):
    """API endpoint for getting extraction result"""
    # Check extraction state
    state = ExtractionState.get_state(extraction_id)
    
    if not state:
        return jsonify({
            'found': False,
            'completed': False,
            'message': 'Extraction not found'
        })
    
    # If extraction is not complete, return status
    if state['progress'] < 100 and not state['stopped']:
        return jsonify({
            'found': True,
            'completed': False,
            'progress': state['progress'],
            'stage': state['stage']
        })
    
    # If extraction is complete, get result from database
    url = state.get('url', '')
    company_data = data_repository.get_company(url)
    
    if not company_data:
        return jsonify({
            'found': True,
            'completed': True,
            'success': False,
            'message': 'Extraction result not found in database'
        })
    
    # Return extraction result
    return jsonify({
        'found': True,
        'completed': True,
        'success': True,
        'data': company_data
    })


@app.route('/api/pause-extraction/<extraction_id>', methods=['POST'])
def api_pause_extraction(extraction_id):
    """API endpoint for pausing extraction"""
    ExtractionState.pause(extraction_id)
    return jsonify({'success': True, 'message': 'Extraction paused'})


@app.route('/api/resume-extraction/<extraction_id>', methods=['POST'])
def api_resume_extraction(extraction_id):
    """API endpoint for resuming extraction"""
    ExtractionState.resume(extraction_id)
    return jsonify({'success': True, 'message': 'Extraction resumed'})


@app.route('/api/stop-extraction/<extraction_id>', methods=['POST'])
def api_stop_extraction(extraction_id):
    """API endpoint for stopping extraction"""
    ExtractionState.stop(extraction_id)
    return jsonify({'success': True, 'message': 'Extraction stopped'})


@app.route('/batch', methods=['GET', 'POST'])
def batch():
    """Batch extraction page"""
    if request.method == 'POST':
        # Check if file was uploaded
        if 'file' not in request.files:
            return render_template('batch.html', error="No file provided")
        
        file = request.files['file']
        if file.filename == '':
            return render_template('batch.html', error="No file selected")
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Read URLs from file
        urls = []
        with open(file_path, 'r') as f:
            for line in f:
                url = line.strip()
                if url:
                    # Ensure URL has protocol
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                    urls.append(url)
        
        if not urls:
            return render_template('batch.html', error="No valid URLs found in file")
        
        # Generate batch ID
        batch_id = f"batch-{int(time.time())}"
        
        # Store batch info
        concurrency = int(request.form.get('concurrency', 5))
        app.config[f'batch_{batch_id}'] = {
            'urls': urls,
            'total': len(urls),
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'failures': [],
            'status': 'processing',
            'start_time': datetime.now().isoformat()
        }
        
        # Start batch process in background
        def batch_callback(result):
            app.config[f'batch_{batch_id}'].update({
                'processed': result['processed'],
                'successful': result['successful'],
                'failed': result['failed'],
                'failures': result['failures'],
                'status': 'completed',
                'end_time': datetime.now().isoformat()
            })
        
        run_async_task(
            extraction_service.process_batch_urls(urls, concurrency),
            callback=batch_callback
        )
        
        # Redirect to batch status page
        return redirect(url_for('batch_status', batch_id=batch_id))
    
    # GET request
    return render_template('batch.html')


@app.route('/batch-status/<batch_id>')
def batch_status(batch_id):
    """Show batch extraction status"""
    return render_template('batch_status.html', batch_id=batch_id)


@app.route('/api/batch-status/<batch_id>')
def api_batch_status(batch_id):
    """API endpoint for getting batch extraction status"""
    batch_info = app.config.get(f'batch_{batch_id}')
    
    if not batch_info:
        return jsonify({
            'found': False,
            'message': 'Batch not found'
        })
    
    return jsonify({
        'found': True,
        'status': batch_info['status'],
        'total': batch_info['total'],
        'processed': batch_info['processed'],
        'successful': batch_info['successful'],
        'failed': batch_info['failed'],
        'progress': int(batch_info['processed'] / batch_info['total'] * 100) if batch_info['total'] > 0 else 0,
        'start_time': batch_info['start_time'],
        'end_time': batch_info.get('end_time')
    })


@app.route('/api/batch-failures/<batch_id>')
def api_batch_failures(batch_id):
    """API endpoint for getting batch extraction failures"""
    batch_info = app.config.get(f'batch_{batch_id}')
    
    if not batch_info:
        return jsonify({
            'found': False,
            'message': 'Batch not found'
        })
    
    return jsonify({
        'found': True,
        'failures': batch_info.get('failures', [])
    })


@app.route('/results')
def results():
    """Show extraction results"""
    # Get search parameters
    search = {}
    for key in ['company_name', 'company_type', 'status', 'date_from', 'date_to']:
        if request.args.get(key):
            search[key] = request.args.get(key)
    
    if request.args.get('has_email') == 'true':
        search['has_email'] = True
    
    if request.args.get('has_products') == 'true':
        search['has_products'] = True
    
    # Get page parameter
    try:
        page = max(1, int(request.args.get('page', 1)))
    except:
        page = 1
    
    # Get limit parameter
    try:
        limit = min(100, max(10, int(request.args.get('limit', 20))))
    except:
        limit = 20
    
    # Get results
    results = data_repository.search_companies(search, limit=limit)
    
    # Get company types for filter dropdown
    conn = sqlite3.connect(data_repository.db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT company_type FROM companies WHERE company_type IS NOT NULL AND company_type != ""')
    company_types = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return render_template(
        'results.html',
        results=results,
        search=search,
        company_types=company_types,
        page=page,
        limit=limit
    )


@app.route('/company/<company_id>')
def company_detail(company_id):
    """Show company detail page"""
    conn = sqlite3.connect(data_repository.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get company data
    cursor.execute('SELECT * FROM companies WHERE id = ?', (company_id,))
    company = cursor.fetchone()
    
    if not company:
        return render_template('error.html', message="Company not found")
    
    # Get products for this company
    cursor.execute('SELECT * FROM products WHERE company_id = ?', (company_id,))
    products = cursor.fetchall()
    
    conn.close()
    
    return render_template(
        'company_detail.html',
        company=company,
        products=products
    )


@app.route('/export', methods=['GET', 'POST'])
def export():
    """Export data page"""
    if request.method == 'POST':
        # Get export format
        export_format = request.form.get('format', 'csv')
        
        # Get filter parameters
        search = {}
        for key in ['company_name', 'company_type', 'status', 'date_from', 'date_to']:
            if request.form.get(key):
                search[key] = request.form.get(key)
        
        if request.form.get('has_email') == 'on':
            search['has_email'] = True
        
        if request.form.get('has_products') == 'on':
            search['has_products'] = True
        
        # Generate export filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"extraction_export_{timestamp}.{export_format}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Generate export
        if export_format == 'csv':
            success = data_repository.export_to_csv(file_path, search)
        else:  # json
            success = data_repository.export_to_json(file_path, search)
        
        if not success:
            return render_template('export.html', error="Export failed")
        
        # Return download link
        download_url = url_for('download_file', filename=filename)
        return render_template('export.html', success=True, download_url=download_url, filename=filename)
    
    # GET request
    return render_template('export.html')


@app.route('/downloads/<filename>')
def download_file(filename):
    """Download a file"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Settings page"""
    if request.method == 'POST':
        # Handle API key updates
        api_keys = {}
        
        for key in [
            'azure_openai_key', 'azure_openai_endpoint', 'azure_openai_deployment',
            'knowledge_graph_api_key', 'google_vision_api_key', 'google_vertex_api_key'
        ]:
            if request.form.get(key):
                api_keys[key] = request.form.get(key)
        
        # Update config
        config.update_api_keys(api_keys)
        
        # Handle other settings
        for key in ['TIMEOUT_SECONDS', 'MAX_RETRIES', 'MAX_PRODUCT_PAGES']:
            if request.form.get(key):
                try:
                    value = int(request.form.get(key))
                    config.set(key, value)
                except:
                    pass
        
        for key in ['ENABLE_ADVANCED_FEATURES', 'FALLBACK_TO_BASIC', 'EXTRACTION.FOLLOW_LINKS', 'EXTRACTION.EXTRACT_IMAGES']:
            value = request.form.get(key) == 'on'
            config.set(key, value)
        
        # Save config
        config.save_config()
        
        return render_template('settings.html', success=True, api_keys=config.get_api_keys(), config=config.config)
    
    # GET request
    return render_template('settings.html', api_keys=config.get_api_keys(), config=config.config)


@app.route('/logs')
def logs():
    """Logs page"""
    # Get log type
    log_type = request.args.get('type', 'extraction')
    
    # Get logs
    if log_type == 'extraction':
        log_entries = log_repository.get_recent_operations(limit=100)
    else:  # error
        log_entries = log_repository.get_recent_errors(limit=100)
    
    return render_template('logs.html', log_type=log_type, logs=log_entries)


@app.route('/api/stats')
def api_stats():
    """API endpoint for getting statistics"""
    return jsonify(global_stats.to_dict())


@app.route('/stats')
def stats():
    """Statistics page"""
    return render_template('stats.html')


def create_app():
    """Create and configure the Flask app"""
    return app


def run_app(host=None, port=None, debug=None):
    """Run the Flask app"""
    host = host or config.get("WEB_UI.HOST", "127.0.0.1")
    port = port or config.get("WEB_UI.PORT", 8080)
    debug = debug if debug is not None else config.get("WEB_UI.DEBUG", True)
    
    print(f"Starting Web Stryker R7 web application on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_app()
