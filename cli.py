#!/usr/bin/env python
"""
Command Line Interface for Web Stryker R7 Python Edition
Provides command-line access to extraction functionality
"""
import os
import sys
import time
import asyncio
import argparse
from typing import List, Dict, Any, Optional
import urllib.parse

# Add parent directory to path if running as script
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import application modules
from domain_models import ExtractionState, global_stats
from config import config
from logging_system import log_repository
from extraction_service import extraction_service
from data_repository import data_repository


class CLI:
    """Command line interface for Web Stryker R7"""
    
    def __init__(self):
        """Initialize CLI"""
        self.parser = self._setup_argument_parser()
    
    def _setup_argument_parser(self) -> argparse.ArgumentParser:
        """Set up command line argument parser"""
        parser = argparse.ArgumentParser(
            description="Web Stryker R7 - Advanced Web Data Extraction Tool",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  Extract data from a single URL:
    python cli.py extract https://example.com
  
  Process multiple URLs from a file:
    python cli.py batch urls.txt
  
  Export extraction results to CSV:
    python cli.py export output.csv
  
  Update configuration:
    python cli.py config --set API.AZURE.OPENAI.KEY=your-key
            """
        )
        
        subparsers = parser.add_subparsers(dest="command", help="Command to execute")
        
        # Extract command
        extract_parser = subparsers.add_parser("extract", help="Extract data from a URL")
        extract_parser.add_argument("url", help="URL to extract data from")
        extract_parser.add_argument("-o", "--output", help="Output file path (JSON format)")
        extract_parser.add_argument("--no-store", action="store_true", help="Don't store results in database")
        
        # Batch command
        batch_parser = subparsers.add_parser("batch", help="Process multiple URLs from a file")
        batch_parser.add_argument("file", help="File containing URLs (one per line)")
        batch_parser.add_argument("-c", "--concurrency", type=int, default=5, help="Number of concurrent extractions (default: 5)")
        batch_parser.add_argument("-o", "--output", help="Output directory for results")
        
        # List command
        list_parser = subparsers.add_parser("list", help="List recent extractions")
        list_parser.add_argument("-l", "--limit", type=int, default=10, help="Number of results to show (default: 10)")
        list_parser.add_argument("-f", "--filter", help="Filter results (format: key=value,key=value)")
        
        # Export command
        export_parser = subparsers.add_parser("export", help="Export extraction results")
        export_parser.add_argument("file", help="Output file path (.csv or .json)")
        export_parser.add_argument("-f", "--filter", help="Filter results (format: key=value,key=value)")
        
        # Config command
        config_parser = subparsers.add_parser("config", help="View or update configuration")
        config_parser.add_argument("--view", action="store_true", help="View current configuration")
        config_parser.add_argument("--set", help="Set configuration value (format: key=value)")
        config_parser.add_argument("--api-keys", action="store_true", help="Interactive API key setup")
        
        # Stats command
        stats_parser = subparsers.add_parser("stats", help="Show extraction statistics")
        
        return parser
    
    async def run(self, args: Optional[List[str]] = None) -> int:
        """Run CLI with given arguments
        
        Args:
            args: Command line arguments (if None, use sys.argv)
            
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        args = self.parser.parse_args(args)
        
        if not args.command:
            self.parser.print_help()
            return 1
        
        if args.command == "extract":
            return await self._handle_extract(args)
        elif args.command == "batch":
            return await self._handle_batch(args)
        elif args.command == "list":
            return self._handle_list(args)
        elif args.command == "export":
            return self._handle_export(args)
        elif args.command == "config":
            return self._handle_config(args)
        elif args.command == "stats":
            return self._handle_stats(args)
        else:
            print(f"Unknown command: {args.command}")
            return 1
    
    async def _handle_extract(self, args) -> int:
        """Handle extract command"""
        print(f"Extracting data from: {args.url}")
        
        try:
            # Generate extraction ID
            extraction_id = f"cli-{int(time.time())}"
            
            # Set up progress reporting
            self._setup_progress_reporting(extraction_id)
            
            # Process URL
            result = await extraction_service.process_url(args.url, extraction_id)
            
            if not result["success"]:
                print(f"Error: {result.get('error', 'Unknown error')}")
                return 1
            
            # Print success message
            print(f"\nExtraction completed in {result.get('duration_ms', 0)/1000:.2f} seconds")
            
            # Print basic information
            company_data = result["data"]
            print(f"\nCompany: {company_data.get('company_name', 'Unknown')}")
            print(f"Type: {company_data.get('company_type', 'Not determined')}")
            print(f"Contact: {company_data.get('emails', 'No email found')}")
            
            if company_data.get('product_name'):
                print(f"Product: {company_data.get('product_name')}")
                if company_data.get('price'):
                    print(f"Price: {company_data.get('price')}")
            else:
                print("No products found")
            
            # Store in database if not disabled
            if not args.no_store:
                company_id = data_repository.store_company(company_data)
                if company_id > 0:
                    print(f"Data stored in database (ID: {company_id})")
            
            # Save to file if output specified
            if args.output:
                os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
                with open(args.output, 'w', encoding='utf-8') as f:
                    import json
                    json.dump(company_data, f, indent=2, ensure_ascii=False)
                print(f"Data saved to {args.output}")
            
            return 0
            
        except KeyboardInterrupt:
            print("\nExtraction canceled by user")
            return 130  # Standard exit code for SIGINT
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1
    
    def _setup_progress_reporting(self, extraction_id: str) -> None:
        """Set up progress reporting for extraction"""
        import threading
        
        # Function to check progress
        def check_progress():
            last_progress = 0
            last_stage = ""
            
            while True:
                state = ExtractionState.get_state(extraction_id)
                if not state:
                    break
                
                progress = state["progress"]
                stage = state["stage"]
                
                # Only print if progress changed
                if progress != last_progress or stage != last_stage:
                    self._print_progress_bar(progress, stage)
                    last_progress = progress
                    last_stage = stage
                
                # Break if completed or stopped
                if state["stopped"] or progress >= 100:
                    break
                
                time.sleep(0.5)
        
        # Start progress checker thread
        thread = threading.Thread(target=check_progress)
        thread.daemon = True
        thread.start()
    
    def _print_progress_bar(self, progress: int, stage: str) -> None:
        """Print progress bar"""
        bar_length = 30
        filled_length = int(bar_length * progress // 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        print(f"\r[{bar}] {progress}% - {stage}", end='')
        sys.stdout.flush()
    
    async def _handle_batch(self, args) -> int:
        """Handle batch command"""
        try:
            # Read URLs from file
            with open(args.file, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
            
            # Filter out invalid URLs
            valid_urls = []
            for url in urls:
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                try:
                    urllib.parse.urlparse(url)
                    valid_urls.append(url)
                except:
                    print(f"Skipping invalid URL: {url}")
            
            if not valid_urls:
                print("No valid URLs found in file")
                return 1
            
            print(f"Processing {len(valid_urls)} URLs with concurrency {args.concurrency}...")
            
            # Process batch
            result = await extraction_service.process_batch_urls(valid_urls, args.concurrency)
            
            # Print results
            print(f"\nCompleted: {result['processed']}/{result['total']}")
            print(f"Successful: {result['successful']}")
            print(f"Failed: {result['failed']}")
            
            if result['failures']:
                print("\nFailed URLs:")
                for failure in result['failures']:
                    print(f"  {failure['url']}: {failure['error']}")
            
            # Create output directory if specified
            if args.output:
                os.makedirs(args.output, exist_ok=True)
                print(f"\nGenerating reports in {args.output}...")
                
                # Export all data to CSV
                csv_path = os.path.join(args.output, "extraction_results.csv")
                if data_repository.export_to_csv(csv_path):
                    print(f"CSV report saved to {csv_path}")
                
                # Export all data to JSON
                json_path = os.path.join(args.output, "extraction_results.json")
                if data_repository.export_to_json(json_path):
                    print(f"JSON report saved to {json_path}")
            
            return 0 if result['successful'] > 0 else 1
            
        except KeyboardInterrupt:
            print("\nBatch processing canceled by user")
            return 130
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_list(self, args) -> int:
        """Handle list command"""
        try:
            # Parse filter if provided
            filter_dict = {}
            if args.filter:
                filter_parts = args.filter.split(',')
                for part in filter_parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        filter_dict[key.strip()] = value.strip()
            
            # Get recent extractions
            results = data_repository.search_companies(filter_dict, args.limit)
            
            if not results:
                print("No extraction results found")
                return 0
            
            # Print results
            print(f"Recent extractions ({len(results)}):")
            print("-" * 80)
            format_str = "{:<40} {:<30} {:<10}"
            print(format_str.format("URL", "Company Name", "Status"))
            print("-" * 80)
            
            for result in results:
                url = result['url']
                if len(url) > 38:
                    url = url[:35] + "..."
                    
                company_name = result['company_name'] or "Unknown"
                if len(company_name) > 28:
                    company_name = company_name[:25] + "..."
                    
                status = result['status'] or "Unknown"
                
                print(format_str.format(url, company_name, status))
            
            return 0
            
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_export(self, args) -> int:
        """Handle export command"""
        try:
            # Parse filter if provided
            filter_dict = {}
            if args.filter:
                filter_parts = args.filter.split(',')
                for part in filter_parts:
                    if '=' in part:
                        key, value = part.split('=', 1)
                        filter_dict[key.strip()] = value.strip()
            
            # Determine export format from file extension
            file_path = args.file
            if file_path.lower().endswith('.csv'):
                print(f"Exporting data to CSV: {file_path}")
                success = data_repository.export_to_csv(file_path, filter_dict)
            elif file_path.lower().endswith('.json'):
                print(f"Exporting data to JSON: {file_path}")
                success = data_repository.export_to_json(file_path, filter_dict)
            else:
                print("Unsupported file format. Use .csv or .json extension")
                return 1
            
            if success:
                print("Export completed successfully")
                return 0
            else:
                print("Export failed")
                return 1
                
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1
    
    def _handle_config(self, args) -> int:
        """Handle config command"""
        try:
            if args.view:
                # Print configuration
                print("Current configuration:")
                self._print_config(config.config)
                return 0
            
            elif args.set:
                # Set configuration value
                if '=' not in args.set:
                    print("Invalid format. Use key=value")
                    return 1
                
                key, value = args.set.split('=', 1)
                
                # Try to parse value as int, float, or bool
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                elif value.isdigit():
                    value = int(value)
                elif value.replace('.', '', 1).isdigit():
                    value = float(value)
                
                config.set(key, value)
                config.save_config()
                
                print(f"Configuration updated: {key} = {value}")
                return 0
            
            elif args.api_keys:
                # Interactive API key setup
                return self._interactive_api_setup()
            
            else:
                print("No action specified. Use --view, --set, or --api-keys")
                return 1
                
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1
    
    def _print_config(self, config_dict, prefix=""):
        """Print configuration recursively"""
        for key, value in config_dict.items():
            if isinstance(value, dict):
                self._print_config(value, prefix + key + ".")
            else:
                # Mask API keys
                if "KEY" in key and value:
                    value = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "****"
                print(f"{prefix}{key} = {value}")
    
    def _interactive_api_setup(self) -> int:
        """Interactive API key setup"""
        print("=== API Key Configuration ===")
        print("Enter API keys (press Enter to skip/keep current value)")
        
        api_keys = config.get_api_keys()
        
        # Azure OpenAI
        print("\n--- Azure OpenAI ---")
        azure_key = input(f"API Key [{self._mask_key(api_keys['azure_openai_key'])}]: ")
        if azure_key:
            api_keys['azure_openai_key'] = azure_key
        
        azure_endpoint = input(f"Endpoint [{api_keys['azure_openai_endpoint']}]: ")
        if azure_endpoint:
            api_keys['azure_openai_endpoint'] = azure_endpoint
        
        azure_deployment = input(f"Deployment Name [{api_keys['azure_openai_deployment']}]: ")
        if azure_deployment:
            api_keys['azure_openai_deployment'] = azure_deployment
        
        # Google Knowledge Graph
        print("\n--- Google Knowledge Graph ---")
        kg_key = input(f"API Key [{self._mask_key(api_keys['knowledge_graph_api_key'])}]: ")
        if kg_key:
            api_keys['knowledge_graph_api_key'] = kg_key
        
        # Google Cloud Vision
        print("\n--- Google Cloud Vision ---")
        vision_key = input(f"API Key [{self._mask_key(api_keys['google_vision_api_key'])}]: ")
        if vision_key:
            api_keys['google_vision_api_key'] = vision_key
        
        # Update config
        config.update_api_keys(api_keys)
        print("\nAPI keys updated successfully")
        
        return 0
    
    def _mask_key(self, key: str) -> str:
        """Mask API key for display"""
        if not key:
            return ""
        return key[:4] + "*" * (len(key) - 8) + key[-4:] if len(key) > 8 else "****"
    
    def _handle_stats(self, args) -> int:
        """Handle stats command"""
        try:
            stats = global_stats.to_dict()
            
            print("=== Extraction Statistics ===")
            print(f"Processed: {stats['processed']}")
            print(f"Successful: {stats['success']}")
            print(f"Failed: {stats['fail']}")
            print(f"Remaining: {stats['remaining']}")
            
            print("\n--- API Calls ---")
            print(f"Azure OpenAI: {stats['api_calls']['azure']['success']} successful, {stats['api_calls']['azure']['fail']} failed")
            print(f"Knowledge Graph: {stats['api_calls']['knowledge_graph']['success']} successful, {stats['api_calls']['knowledge_graph']['fail']} failed")
            
            print("\n--- Company Data ---")
            print(f"Companies found: {stats['company_data']['found']}")
            print(f"Emails extracted: {stats['company_data']['emails']}")
            print(f"Phones extracted: {stats['company_data']['phones']}")
            print(f"Addresses extracted: {stats['company_data']['addresses']}")
            
            print("\n--- Product Data ---")
            print(f"Products found: {stats['product_data']['found']}")
            print(f"Images extracted: {stats['product_data']['images']}")
            print(f"Descriptions extracted: {stats['product_data']['descriptions']}")
            print(f"Categories identified: {stats['product_data']['categories']}")
            
            return 0
            
        except Exception as e:
            print(f"Error: {str(e)}")
            return 1


def main():
    """Main entry point for CLI"""
    cli = CLI()
    exit_code = asyncio.run(cli.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
