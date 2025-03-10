# Web Stryker R7 Python Edition

An advanced web data extraction tool for gathering company and product information from websites.

## Features

- **Robust Extraction**: Extract company information, contact details, and product data from websites
- **AI Enhancement**: Improve extraction quality with AI-powered data enrichment
- **Multiple Interfaces**: Use command line interface, web UI, or Python API
- **Parallel Processing**: Extract from multiple URLs simultaneously
- **Data Storage**: Store and search extracted data in SQLite database
- **Export Options**: Export data to CSV or JSON formats
- **Customizable**: Configure extraction parameters to suit your needs

## Installation

### Requirements

- Python 3.7 or higher
- pip package manager

### Installation Steps

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/web-stryker-python.git
   cd web-stryker-python
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Run the setup script:
   ```
   python main.py --setup
   ```

## Usage

### Command Line Interface

Extract data from a single URL:
```
python main.py extract https://example.com
```

Process multiple URLs from a file:
```
python main.py batch urls.txt
```

Export extraction results to CSV:
```
python main.py export output.csv
```

Get more help:
```
python main.py --help
```

### Web Interface

Start the web application:
```
python main.py --web
```

Then open your browser and navigate to http://localhost:8080

### Python API

```python
import asyncio
from extraction_service import extraction_service
from data_repository import data_repository

# Extract data from a URL
async def extract_url(url):
    extraction_id = "api-example"
    result = await extraction_service.process_url(url, extraction_id)
    
    if result["success"]:
        print(f"Extraction successful: {result['data']['company_name']}")
        
        # Store in database
        data_repository.store_company(result["data"])
    else:
        print(f"Extraction failed: {result['error']}")

# Run the extraction
asyncio.run(extract_url("https://example.com"))
```

## Configuration

The application configuration is stored in a JSON file located at `~/.web_stryker/config.json`. You can modify this file directly or use the configuration tools:

```
python main.py config --view  # View current configuration
python main.py config --set API.AZURE.OPENAI.KEY=your-key  # Set configuration value
python main.py config --api-keys  # Interactive API key setup
```

### API Keys

For enhanced extraction capabilities, you can configure the following API keys:

- **Azure OpenAI**: For AI-powered data enrichment
- **Google Knowledge Graph**: For entity recognition and validation
- **Google Cloud Vision**: For image analysis (optional)

## Project Structure

```
web-stryker-python/
│
├── domain_models.py        # Core domain entities
├── config.py               # Configuration system
├── logging_system.py       # Logging utilities
├── extractors_base.py      # Base extraction classes
├── extraction_service.py   # Main extraction service
├── data_repository.py      # Data storage and retrieval
├── web_application.py      # Flask web application
├── cli.py                  # Command line interface
├── main.py                 # Main entry point
│
├── templates/              # Web UI templates
├── static/                 # Web UI static assets
├── logs/                   # Log files
├── data/                   # Data storage
└── uploads/                # Uploaded files
```

## Advanced Features

### Batch Processing

Process multiple URLs in parallel:

```
python main.py batch urls.txt --concurrency 10
```

### Search and Filter

Search for specific companies in the database:

```
python main.py list --filter "company_type=Technology,has_products=true"
```

### Data Export

Export filtered data:

```
python main.py export output.csv --filter "company_type=Retail"
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributions

Contributions are welcome! Please feel free to submit a Pull Request.
