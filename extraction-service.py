"""
Extraction Service for Web Stryker R7 Python Edition
Main service for coordinating the extraction process
"""
import time
import uuid
import traceback
import re
import requests
from typing import Dict, Any, Optional, Tuple, List
from urllib.parse import urlparse

# Import domain models and extractors
from domain_models import CompanyEntity, ProductEntity, ExtractionState, global_stats
from config import config
from logging_system import log_repository, log_execution_time
from extractors_base import CompanyExtractor, ContactExtractor, ProductExtractor


class AiEnricher:
    """Enriches data using AI services"""
    
    def __init__(self, config_data: Dict[str, Any]):
        """Initialize with configuration"""
        self.config = config_data
        self.azure_enabled = bool(self.config.get("API.AZURE.OPENAI.KEY"))
        self.kg_enabled = bool(self.config.get("API.KNOWLEDGE_GRAPH.KEY"))
    
    @log_execution_time()
    async def enrich_data(self, company: CompanyEntity) -> None:
        """Enrich company data with AI"""
        # Skip if no API key or endpoint
        if not self.azure_enabled:
            return
        
        api_key = self.config.get("API.AZURE.OPENAI.KEY")
        endpoint = self.config.get("API.AZURE.OPENAI.ENDPOINT")
        deployment = self.config.get("API.AZURE.OPENAI.DEPLOYMENT")
        
        # Skip if missing any configuration
        if not (api_key and endpoint and deployment):
            return
        
        try:
            # Prepare prompt for company data enrichment
            prompt = f"""
                Analyze this company data and provide enriched information:
                
                Company Name: {company.company_name or 'Unknown'}
                Company Description: {company.company_description or 'None provided'}
                Company Type/Industry: {company.company_type or 'Unknown'}
                Products: {', '.join(p.product_name for p in company.products) if company.products else 'None found'}
                
                Please provide:
                1. A more accurate company type/industry classification
                2. A categorization of the products found
                3. If the company appears to be focused on specific markets or demographics
                
                Format your response as JSON with keys: refinedCompanyType, productCategories, targetMarket
            """
            
            # Call Azure OpenAI API
            api_url = f"{endpoint}openai/deployments/{deployment}/chat/completions?api-version=2023-05-15"
            
            request_body = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an AI assistant that specializes in analyzing company and product information to provide structured business intelligence data."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": self.config.get("API.AZURE.OPENAI.TEMPERATURE", 0.3),
                "max_tokens": self.config.get("API.AZURE.OPENAI.MAX_TOKENS", 1000)
            }
            
            headers = {
                "Content-Type": "application/json",
                "api-key": api_key
            }
            
            response = requests.post(api_url, headers=headers, json=request_body, timeout=30)
            response_data = response.json()
            
            if "error" in response_data:
                log_repository.log_error(
                    company.url, "unknown", "AzureOpenAIError", 
                    f"Azure OpenAI API error: {response_data['error'].get('message', 'Unknown error')}"
                )
                global_stats.api_calls["azure"]["fail"] += 1
                return
            
            if "choices" in response_data and response_data["choices"]:
                try:
                    ai_response = response_data["choices"][0]["message"]["content"]
                    
                    # Extract JSON from response text
                    import json
                    import re
                    
                    json_match = re.search(r'\{[\s\S]*\}', ai_response)
                    if json_match:
                        enriched_data = json.loads(json_match.group(0))
                        
                        # Update company entity with enriched data
                        if ("refinedCompanyType" in enriched_data and 
                           (not company.company_type or company.company_type == "Other" or company.company_type == "Technology")):
                            company.company_type = enriched_data["refinedCompanyType"]
                        
                        # Add main category to products if available
                        if "productCategories" in enriched_data:
                            category = (enriched_data["productCategories"][0] 
                                       if isinstance(enriched_data["productCategories"], list) 
                                       else enriched_data["productCategories"])
                            
                            for product in company.products:
                                if not product.main_category:
                                    product.main_category = category
                        
                        # Update global stats
                        global_stats.api_calls["azure"]["success"] += 1
                    
                except Exception as e:
                    log_repository.log_error(
                        company.url, "unknown", "AIParseError", 
                        f"Error parsing AI response: {str(e)}"
                    )
                    global_stats.api_calls["azure"]["fail"] += 1
            
        except Exception as e:
            log_repository.log_error(
                company.url, "unknown", "AIEnrichmentError", 
                f"Error enriching data with AI: {str(e)}"
            )
            global_stats.api_calls["azure"]["fail"] += 1
    
    async def query_knowledge_graph(self, company: CompanyEntity) -> None:
        """Query Google Knowledge Graph API for company info"""
        try:
            # Skip if no API key or company name
            if not self.kg_enabled or not company.company_name:
                return
            
            api_key = self.config.get("API.KNOWLEDGE_GRAPH.KEY")
            import urllib.parse
            
            # URL encode the query
            encoded_query = urllib.parse.quote(company.company_name)
            api_url = f"https://kgsearch.googleapis.com/v1/entities:search?query={encoded_query}&key={api_key}&limit=1&types=Organization&types=Corporation"
            
            response = requests.get(api_url, timeout=30)
            response_data = response.json()
            
            if "itemListElement" in response_data and response_data["itemListElement"]:
                item = response_data["itemListElement"][0].get("result", {})
                
                # Update company type if not already set
                if "description" in item and (not company.company_type or company.company_type == "Other"):
                    company.company_type = item["description"]
                
                # Update company description if available and better than current
                if "detailedDescription" in item and "articleBody" in item["detailedDescription"]:
                    new_description = item["detailedDescription"]["articleBody"]
                    if not company.company_description or len(new_description) > len(company.company_description):
                        company.company_description = new_description
                
                # Update global stats
                global_stats.api_calls["knowledge_graph"]["success"] += 1
                
        except Exception as e:
            log_repository.log_error(
                company.url, "unknown", "KnowledgeGraphError", 
                f"Error querying Knowledge Graph: {str(e)}"
            )
            global_stats.api_calls["knowledge_graph"]["fail"] += 1


class ExtractionService:
    """Main service for extracting data"""
    
    def __init__(self):
        """Initialize extraction service"""
        self.config_data = config
    
    def validate_url(self, url: str) -> bool:
        """Validate URL format"""
        try:
            url_pattern = r'^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$'
            return bool(re.match(url_pattern, url, re.IGNORECASE))
        except Exception:
            return False
    
    async def fetch_content(self, url: str, extraction_id: str) -> Optional[str]:
        """Fetch content from URL with retry logic"""
        headers = {
            "User-Agent": self.config_data.get("USER_AGENT", "Mozilla/5.0 (compatible; WebStrykerPython/1.0)"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        
        max_retries = self.config_data.get("MAX_RETRIES", 3)
        timeout_seconds = self.config_data.get("TIMEOUT_SECONDS", 30)
        
        for attempt in range(max_retries):
            # Check if extraction is stopped
            if ExtractionState.is_stopped(extraction_id):
                print("Extraction stopped during fetch")
                return None
            
            # Wait if paused
            if ExtractionState.is_paused(extraction_id):
                while ExtractionState.is_paused(extraction_id) and not ExtractionState.is_stopped(extraction_id):
                    time.sleep(0.5)
            
            try:
                response = requests.get(url, headers=headers, timeout=timeout_seconds)
                
                # Check if response is successful
                if response.status_code == 200:
                    return response.text
                
                # Log error but continue to retry
                log_repository.log_error(
                    url, extraction_id, "FetchError", 
                    f"Failed to fetch content: HTTP {response.status_code}"
                )
                
            except requests.RequestException as e:
                log_repository.log_error(
                    url, extraction_id, "FetchError", 
                    f"Fetch attempt {attempt + 1} failed: {str(e)}"
                )
            
            # Add exponential backoff with jitter
            import random
            sleep_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(sleep_time)
        
        log_repository.log_error(
            url, extraction_id, "FetchError", 
            f"All {max_retries} retry attempts failed for {url}"
        )
        return None
    
    @log_execution_time()
    async def extract_data(self, url: str, extraction_id: str, extraction_state: ExtractionState) -> Optional[CompanyEntity]:
        """Extract company and product data"""
        # Fetch the URL content
        extraction_state.update_progress(15, "Fetching website content")
        content = await self.fetch_content(url, extraction_id)
        if not content:
            return None
        
        # Create company entity
        company = CompanyEntity()
        company.url = url
        
        # Extract company information
        extraction_state.update_progress(25, "Extracting company information")
        company_extractor = CompanyExtractor(self.config_data)
        company_extractor.extract(content, url, company)
        
        # Extract contact information
        extraction_state.update_progress(40, "Extracting contact information")
        contact_extractor = ContactExtractor(self.config_data)
        contact_extractor.extract(content, url, company)
        
        # Extract product information
        extraction_state.update_progress(60, "Discovering product information")
        product_extractor = ProductExtractor(self.config_data)
        product_extractor.extract(content, url, company, extraction_id)
        
        # Enrich data with AI if available
        extraction_state.update_progress(80, "Enriching data with AI analysis")
        ai_enricher = AiEnricher(self.config_data)
        
        # Use OpenAI if configured
        if self.config_data.get("API.AZURE.OPENAI.KEY"):
            await ai_enricher.enrich_data(company)
        
        # Also try Knowledge Graph if configured
        if self.config_data.get("API.KNOWLEDGE_GRAPH.KEY") and company.company_name:
            await ai_enricher.query_knowledge_graph(company)
        
        return company
    
    async def process_url(self, url: str, extraction_id: str) -> Dict[str, Any]:
        """Process a URL for extraction"""
        try:
            # Start timing the overall extraction
            start_time = time.time()
            
            # Create extraction state
            extraction_state = ExtractionState(extraction_id, url)
            
            # Validate URL
            extraction_state.update_progress(5, "Validating URL")
            if not self.validate_url(url):
                log_repository.log_error(url, extraction_id, "ValidationError", "Invalid URL format")
                return {"success": False, "error": "Invalid URL format"}
            
            # Extract data
            extraction_state.update_progress(10, "Starting extraction")
            extracted_company = await self.extract_data(url, extraction_id, extraction_state)
            
            if not extracted_company:
                log_repository.log_operation(
                    url, extraction_id, "Extraction", "Failed", 
                    "Failed to extract data from URL"
                )
                return {"success": False, "error": "Failed to extract data from URL"}
            
            # Finalize
            extraction_state.update_progress(100, "Completed")
            
            # Calculate total duration
            end_time = time.time()
            total_duration = int((end_time - start_time) * 1000)  # in milliseconds
            
            # Log completion
            log_repository.log_operation(
                url, extraction_id, "Extraction", "Completed", 
                "Extraction completed successfully", total_duration
            )
            
            # Increment global stats
            global_stats.processed += 1
            global_stats.success += 1
            
            # Return results
            return {
                "success": True,
                "data": extracted_company.to_dict(),
                "duration_ms": total_duration
            }
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            error_message = f"Error processing URL: {str(e)}"
            
            log_repository.log_error(
                url, extraction_id, "ProcessingError", 
                error_message, stack_trace
            )
            
            global_stats.fail += 1
            
            return {
                "success": False,
                "error": error_message
            }
    
    async def process_batch_urls(self, urls: List[str], concurrent_limit: int = 5) -> Dict[str, Any]:
        """Process multiple URLs in batch mode with concurrency limit"""
        import asyncio
        
        if not urls:
            return {
                "success": False,
                "error": "No URLs provided"
            }
        
        # Initialize batch results
        batch_id = f"batch-{int(time.time())}"
        results = {
            "batch_id": batch_id,
            "total": len(urls),
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "failures": [],
            "success": True
        }
        
        # Update global stats
        global_stats.remaining = len(urls)
        
        # Process URLs with limited concurrency
        semaphore = asyncio.Semaphore(concurrent_limit)
        
        async def process_url_with_limit(url, index):
            async with semaphore:
                extraction_id = f"{batch_id}-{index}"
                return await self.process_url(url, extraction_id)
        
        # Create tasks for all URLs
        tasks = [process_url_with_limit(url, i) for i, url in enumerate(urls)]
        
        # Process URLs and collect results
        for task in asyncio.as_completed(tasks):
            result = await task
            
            # Update batch results
            results["processed"] += 1
            if result["success"]:
                results["successful"] += 1
            else:
                results["failed"] += 1
                results["failures"].append({
                    "url": result.get("url", "unknown"),
                    "error": result.get("error", "Unknown error")
                })
            
            # Update global stats
            global_stats.remaining -= 1
        
        # Update success flag if any failures
        if results["failed"] > 0:
            results["success"] = False
        
        return results


# Create singleton instance
extraction_service = ExtractionService()
