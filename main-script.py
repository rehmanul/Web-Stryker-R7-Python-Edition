#!/usr/bin/env python
"""
Web Stryker R7 Python Edition
Main entry point for the application
"""
import os
import sys
import argparse
import asyncio
from typing import Optional, List

# Import application modules
from config import config
from logging_system import main_logger
from cli import CLI
from web_application import run_app


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Web Stryker R7 - Advanced Web Data Extraction Tool")
    parser.add_argument("--web", action="store_true", help="Start web application")
    parser.add_argument("--host", type=str, help="Web application host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Web application port (default: 8080)")
    parser.add_argument("--cli", action="store_true", help="Run command line interface")
    parser.add_argument("--setup", action="store_true", help="Run initial setup")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--version", action="store_true", help="Show version information")
    parser.add_argument("command", nargs="?", help="CLI command to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="CLI command arguments")
    return parser.parse_args()


async def main() -> int:
    """Main application entry point"""
    args = parse_args()
    
    # Handle version request
    if args.version:
        print("Web Stryker R7 Python Edition v1.0.0")
        return 0
    
    # Load config from specified path if provided
    if args.config:
        if os.path.exists(args.config):
            # Update config path
            config.config_path = args.config
            config.load_config()
            main_logger.info(f"Loaded configuration from {args.config}")
        else:
            main_logger.error(f"Configuration file not found: {args.config}")
            return 1
    
    # Run initial setup if requested
    if args.setup:
        return await run_setup()
    
    # Start web application if requested
    if args.web:
        host = args.host or config.get("WEB_UI.HOST", "127.0.0.1")
        port = args.port or config.get("WEB_UI.PORT", 8080)
        
        try:
            run_app(host=host, port=port)
            return 0
        except Exception as e:
            main_logger.error(f"Error running web application: {str(e)}")
            return 1
    
    # Run CLI command if provided, or full CLI if --cli flag is set
    if args.command or args.cli:
        cli = CLI()
        cli_args = []
        
        if args.command:
            cli_args.append(args.command)
            if args.args:
                cli_args.extend(args.args)
        
        return await cli.run(cli_args if cli_args else None)
    
    # If no specific mode is requested, show usage information
    print("Web Stryker R7 Python Edition v1.0.0")
    print("\nUsage:")
    print("  python main.py --web           # Start web application")
    print("  python main.py --cli           # Run interactive CLI")
    print("  python main.py extract URL     # Extract data from URL")
    print("  python main.py --setup         # Run initial setup")
    print("  python main.py --version       # Show version information")
    print("\nRun python main.py --help for more information")
    
    return 0


async def run_setup() -> int:
    """Run initial setup"""
    print("=== Web Stryker R7 Initial Setup ===")
    
    # Create necessary directories
    dirs = ["logs", "data", "uploads", "templates", "static"]
    for directory in dirs:
        os.makedirs(directory, exist_ok=True)
        print(f"Created directory: {directory}")
    
    # Ask for API keys
    print("\nAPI Key Configuration (press Enter to skip)")
    
    api_keys = {}
    
    print("\n--- Azure OpenAI ---")
    api_keys["azure_openai_key"] = input("API Key: ").strip()
    
    if api_keys["azure_openai_key"]:
        api_keys["azure_openai_endpoint"] = input("Endpoint [https://fetcher.openai.azure.com/]: ").strip()
        if not api_keys["azure_openai_endpoint"]:
            api_keys["azure_openai_endpoint"] = "https://fetcher.openai.azure.com/"
            
        api_keys["azure_openai_deployment"] = input("Deployment Name [gpt-4]: ").strip()
        if not api_keys["azure_openai_deployment"]:
            api_keys["azure_openai_deployment"] = "gpt-4"
    
    print("\n--- Google Knowledge Graph ---")
    api_keys["knowledge_graph_api_key"] = input("API Key: ").strip()
    
    # Update config with API keys
    if any(api_keys.values()):
        config.update_api_keys(api_keys)
        print("\nAPI keys saved to configuration")
    
    # Create sample templates if they don't exist
    if not os.path.exists("templates/index.html"):
        print("\nCreating sample templates...")
        # Save template files (implementation omitted for brevity)
    
    print("\nSetup completed successfully!")
    print("To start the web application, run: python main.py --web")
    print("To use the command line interface, run: python main.py --cli")
    
    return 0


if __name__ == "__main__":
    # Run main function
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
