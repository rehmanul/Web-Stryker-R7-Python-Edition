"""
Base extractors for Web Stryker R7 Python Edition
Contains the core extraction functionality
"""
import re
import time
from abc import ABC, abstractmethod
import traceback
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
import urllib.robotparser
import requests
from bs4 import BeautifulSoup

# Import domain models and utilities
from domain_models import CompanyEntity, ProductEntity, ExtractionState, global_stats
from config import config
from logging_system import log_repository, log_execution_time


class BaseExtractor(ABC):
    """Base class for all extractors"""
    
    def __init__(self, config_data: Dict[str, Any]):
        """Initialize with configuration"""
        self.config = config_data
        self.headers = {
            "User-Agent": self.config.get("USER_AGENT", 
                           "Mozilla/5.0 (compatible; WebStrykerPython/1.0)"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0"
        }
    
    @abstractmethod
    def extract(self, *args, **kwargs):
        """Extract method to be implemented by subclasses"""
        pass
    
    def clean_html(self, html: str) -> str:
        """Clean HTML content to plain text"""
        if not html:
            return ''
        
        # Use BeautifulSoup for better HTML cleaning
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script_or_style in soup(['script', 'style']):
                script_or_style.decompose()
            
            # Get text
            text = soup.get_text()
            
            # Normalize whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            return text
        except Exception as e:
            # Fallback to regex if BeautifulSoup fails
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
    
    def resolve_url(self, url: str, base: str) -> str:
        """Resolve relative URL to absolute URL"""
        try:
            return urljoin(base, url)
        except Exception as e:
            # Return original URL if resolution fails
            return url
    
    def extract_structured_data(self, content: str) -> Dict[str, Any]:
        """Extract structured data from HTML content"""
        try:
            # Look for JSON-LD
            json_ld_match = re.search(
                r'<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>', 
                content, 
                re.IGNORECASE
            )
            
            if json_ld_match:
                import json
                return json.loads(json_ld_match.group(1))
            
            return {}
        except Exception as e:
            # Log error but continue
            log_repository.log_error(
                "unknown", "unknown", "StructuredDataError", 
                f"Error extracting structured data: {str(e)}"
            )
            return {}
    
    def check_robots_txt(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt"""
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            robots_url = urljoin(base_url, "/robots.txt")
            
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.read()
            
            # Check if our user agent is allowed to fetch the URL
            return parser.can_fetch(self.headers["User-Agent"], url)
        except Exception as e:
            # If there's an error checking robots.txt, assume it's allowed
            # but log the error
            log_repository.log_error(
                url, "unknown", "RobotsError", 
                f"Error checking robots.txt: {str(e)}"
            )
            return True


class CompanyExtractor(BaseExtractor):
    """Extracts company information"""
    
    @log_execution_time()
    def extract(self, content: str, url: str, company: CompanyEntity) -> None:
        """Extract company information from HTML content"""
        try:
            # Extract company name (from title, meta tags, or prominent headings)
            title_match = re.search(r'<title>(.*?)<\/title>', content, re.IGNORECASE)
            if title_match:
                # Clean up title to get company name
                title = title_match.group(1).strip()
                
                # Remove common suffixes
                title = re.sub(r'\s*[-|]\s*(Home|Official Website|Official Site|Welcome).*$', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*[-|]\s*.*?(homepage|official).*$', '', title, flags=re.IGNORECASE)
                
                company.company_name = title
            
            # Try to get a more precise company name from structured data
            structured_data = self.extract_structured_data(content)
            if structured_data and 'organization' in structured_data and 'name' in structured_data['organization']:
                company.company_name = structured_data['organization']['name']
            
            # Look for organization name in common patterns
            org_name_match = re.search(
                r'<meta\s+(?:property|name)="(?:og:site_name|twitter:site)"[^>]*content="([^"]*)"[^>]*>',
                content,
                re.IGNORECASE
            )
            if org_name_match:
                company.company_name = org_name_match.group(1).strip()
            
            # Extract company description
            meta_description = re.search(
                r'<meta\s+name="description"\s+content="([^"]*)"',
                content,
                re.IGNORECASE
            )
            if meta_description:
                company.company_description = meta_description.group(1).strip()
            
            # Look for about us sections for better description
            about_section_patterns = [
                r'<(?:div|section)[^>]*\b(?:id|class)="[^"]*\babout\b[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section)>',
                r'<h\d[^>]*>\s*About\s+(?:Us|Company)\s*<\/h\d>([\s\S]*?)(?:<h\d|<\/div|<\/section)'
            ]
            
            for pattern in about_section_patterns:
                about_match = re.search(pattern, content, re.IGNORECASE)
                if about_match:
                    about_text = self.clean_html(about_match.group(1))
                    if len(about_text) > len(company.company_description):
                        company.company_description = about_text
                    break
            
            # Try OG description for better company description
            og_description = re.search(
                r'<meta\s+property="og:description"\s+content="([^"]*)"',
                content,
                re.IGNORECASE
            )
            if og_description and (not company.company_description or 
                                   len(company.company_description) < len(og_description.group(1))):
                company.company_description = og_description.group(1).strip()
            
            # Extract company type
            industry_keywords = [
                {"regex": r'\b(?:tech|software|application|app|digital|IT|information technology)\b', "type": "Technology"},
                {"regex": r'\b(?:manufacturing|factory|production|industrial)\b', "type": "Manufacturing"},
                {"regex": r'\b(?:retail|shop|store|e-commerce|marketplace)\b', "type": "Retail"},
                {"regex": r'\b(?:healthcare|medical|hospital|clinic|pharma|health)\b', "type": "Healthcare"},
                {"regex": r'\b(?:financial|bank|insurance|investment|finance)\b', "type": "Financial Services"},
                {"regex": r'\b(?:food|restaurant|catering|bakery|café)\b', "type": "Food & Beverage"},
                {"regex": r'\b(?:tofu|vegan|plant-based|vegetarian|organic food)\b', "type": "Plant-based Foods"}
            ]
            
            # Check description for industry keywords
            text_to_analyze = company.company_description or content
            
            for industry in industry_keywords:
                if re.search(industry["regex"], text_to_analyze, re.IGNORECASE):
                    company.company_type = industry["type"]
                    break
            
            # Extract logo URL
            logo_patterns = [
                r'<img[^>]*\b(?:id|class)="[^"]*\b(?:logo|brand|company-logo)\b[^"]*"[^>]*src="([^"]*)"',
                r'<img[^>]*\balt="[^"]*\b(?:logo|brand|company-logo)\b[^"]*"[^>]*src="([^"]*)"',
                r'<img[^>]*\bsrc="([^"]*logo[^"]*)"'
            ]
            
            for pattern in logo_patterns:
                logo_match = re.search(pattern, content, re.IGNORECASE)
                if logo_match:
                    company.logo = self.resolve_url(logo_match.group(1), url)
                    break
            
            # Update global stats
            if company.company_name:
                global_stats.company_data["found"] += 1
            if company.company_description:
                global_stats.company_data["descriptions"] += 1
            if company.company_type:
                global_stats.company_data["types"] += 1
                
        except Exception as e:
            stack_trace = traceback.format_exc()
            log_repository.log_error(
                url, "unknown", "CompanyExtractionError", 
                f"Error extracting company info: {str(e)}", 
                stack_trace
            )


class ContactExtractor(BaseExtractor):
    """Extracts contact information"""
    
    @log_execution_time()
    def extract(self, content: str, url: str, company: CompanyEntity) -> None:
        """Extract contact information from HTML content"""
        try:
            # Look for contact page link
            contact_page_url = None
            contact_link_patterns = [
                r'<a[^>]*\bhref="([^"]*contact[^"]*)"',
                r'<a[^>]*\bhref="([^"]*about-us[^"]*)"',
                r'<a[^>]*\bhref="([^"]*get-in-touch[^"]*)"'
            ]
            
            for pattern in contact_link_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    contact_page_url = self.resolve_url(match.group(1), url)
                    break
            
            # If contact page found, fetch and analyze it
            contact_page_content = ""
            if contact_page_url and contact_page_url != url:
                try:
                    response = requests.get(
                        contact_page_url, 
                        headers=self.headers,
                        timeout=self.config.get("TIMEOUT_SECONDS", 30)
                    )
                    if response.status_code == 200:
                        contact_page_content = response.text
                except Exception as e:
                    log_repository.log_error(
                        url, "unknown", "ContactPageFetchError", 
                        f"Error fetching contact page: {str(e)}"
                    )
            
            # Combine main content and contact page content
            combined_content = content + (contact_page_content or "")
            
            # Extract emails
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
            email_matches = re.findall(email_pattern, combined_content)
            
            if email_matches:
                # Filter out common false positives
                false_positives = {'example@example.com', 'user@example.com', 'name@example.com'}
                filtered_emails = [email for email in email_matches if email.lower() not in false_positives]
                
                company.emails = list(set(filtered_emails))  # Remove duplicates
                global_stats.company_data["emails"] += len(company.emails)
            
            # Extract phone numbers
            phone_patterns = [
                r'\b\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}\b',  # International format
                r'\b\(\d{3}\)[\s.-]?\d{3}[\s.-]?\d{4}\b',  # US format (xxx) xxx-xxxx
                r'\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b',      # Simple format xxx-xxx-xxxx
                r'\b\d{2,3}[\s.-]?\d{2,4}[\s.-]?\d{4,5}\b'  # European formats
            ]
            
            found_phones = []
            for pattern in phone_patterns:
                phone_matches = re.findall(pattern, combined_content)
                found_phones.extend(phone_matches)
            
            if found_phones:
                company.phones = list(set(found_phones))  # Remove duplicates
                global_stats.company_data["phones"] += len(company.phones)
            
            # Extract addresses
            # Look for contact section
            contact_section_patterns = [
                r'<(?:div|section)[^>]*\b(?:id|class)="[^"]*\b(?:contact|address|location)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section)>',
                r'<h\d[^>]*>\s*(?:Contact|Address|Location|Find Us)\s*<\/h\d>([\s\S]*?)(?:<h\d|<\/div|<\/section)'
            ]
            
            contact_section = ""
            for pattern in contact_section_patterns:
                match = re.search(pattern, combined_content, re.IGNORECASE)
                if match:
                    contact_section = match.group(1)
                    break
            
            # If contact section found, look for address patterns
            if contact_section:
                # Parse with BeautifulSoup for better content extraction
                soup = BeautifulSoup(contact_section, 'html.parser')
                
                # Look for potential address elements
                address_elements = []
                address_elements.extend(soup.select('p'))
                address_elements.extend(soup.select('div.address, span.address, div.location, span.location'))
                
                for element in address_elements:
                    clean_address = self.clean_html(str(element))
                    
                    # Check if this looks like an address (contains numbers and common address words)
                    if (re.search(r'\d+', clean_address) and 
                        re.search(r'\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|way|place|pl|square|sq|county|city|town|village|state|province|country)\b', 
                                 clean_address, 
                                 re.IGNORECASE)):
                        company.addresses.append(clean_address)
            
            # If no addresses found yet, try generic patterns
            if not company.addresses:
                address_patterns = [
                    # Street, City, State ZIP format
                    r'\d+\s+[A-Za-z0-9\s.,]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl|Square|Sq)[,.\s]*(?:[A-Za-z\s]+)[,.\s]*(?:[A-Z]{2}|\b[A-Za-z]+\b)[,.\s]*(?:\d{5}(?:-\d{4})?)?',
                    
                    # European format
                    r'\d+\s+[A-Za-z0-9\s.,]+\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd)[,.\s]*(?:[A-Za-z\s]+)[,.\s]*(?:[A-Z]{1,2}\d{1,2}\s+\d[A-Z]{2}|\d{4,5})',
                    
                    # P.O. Box format
                    r'P\.?O\.?\s+Box\s+\d+[,.\s]*(?:[A-Za-z\s]+)[,.\s]*(?:[A-Z]{2}|\b[A-Za-z]+\b)[,.\s]*(?:\d{5}(?:-\d{4})?)?'
                ]
                
                for pattern in address_patterns:
                    address_matches = re.findall(pattern, combined_content, re.IGNORECASE)
                    company.addresses.extend([addr.strip() for addr in address_matches])
            
            # Remove duplicates and update stats
            company.addresses = list(set(company.addresses))
            if company.addresses:
                global_stats.company_data["addresses"] += len(company.addresses)
                
        except Exception as e:
            stack_trace = traceback.format_exc()
            log_repository.log_error(
                url, "unknown", "ContactExtractionError", 
                f"Error extracting contact info: {str(e)}", 
                stack_trace
            )


class ProductExtractor(BaseExtractor):
    """Extracts product information"""
    
    def __init__(self, config_data: Dict[str, Any]):
        """Initialize with configuration"""
        super().__init__(config_data)
        self.visited_urls: Set[str] = set()
        self.max_products = self.config.get("EXTRACTION.MAX_PRODUCTS", 20)
        self.max_depth = self.config.get("MAX_CRAWL_DEPTH", 3)
    
    @log_execution_time()
    def extract(self, content: str, url: str, company: CompanyEntity, extraction_id: str) -> None:
        """Extract product information"""
        try:
            # Extract categories from menu structure or breadcrumbs
            categories = self.extract_categories(content)
            
            # Extract product links from the page
            product_links = self.extract_product_links(content, url)
            
            # If no product links found, look for products section link
            if not product_links:
                products_page_url = self.find_products_page(content, url)
                
                # If products page found, fetch and analyze it
                if products_page_url and products_page_url != url:
                    try:
                        response = requests.get(
                            products_page_url, 
                            headers=self.headers, 
                            timeout=self.config.get("TIMEOUT_SECONDS", 30)
                        )
                        if response.status_code == 200:
                            products_page_content = response.text
                            # Extract product links from products page
                            additional_links = self.extract_product_links(products_page_content, products_page_url)
                            product_links.extend(additional_links)
                    except Exception as e:
                        log_repository.log_error(
                            url, extraction_id, "ProductPageFetchError", 
                            f"Error fetching products page: {str(e)}"
                        )
            
            # If still no product links, try to extract product from current page
            if not product_links:
                self.extract_product_from_page(content, url, company)
                return
            
            # Process product links if configured to do so
            if self.config.get("EXTRACTION.FOLLOW_LINKS", True) and product_links:
                # Limit the number of products to process
                links_to_process = product_links[:min(len(product_links), self.max_products)]
                
                # Process each product link
                for i, product_link in enumerate(links_to_process):
                    # Check if extraction is stopped
                    if ExtractionState.is_stopped(extraction_id):
                        break
                    
                    # Wait if paused
                    if ExtractionState.is_paused(extraction_id):
                        while ExtractionState.is_paused(extraction_id) and not ExtractionState.is_stopped(extraction_id):
                            time.sleep(0.5)
                    
                    # Process product page
                    product_data = self.process_product_page(product_link["url"])
                    
                    if product_data:
                        # Create product entity
                        product = ProductEntity()
                        product.product_name = product_data.get("product_name") or product_link.get("text") or ""
                        product.product_url = product_link["url"]
                        product.description = product_data.get("description", "")
                        product.price = product_data.get("price", "")
                        product.quantity = product_data.get("quantity", "")
                        product.specifications = product_data.get("specifications", "")
                        product.images = product_data.get("images", [])
                        
                        # Set category information from global categories
                        if categories:
                            product.main_category = categories[0] if categories else ""
                            if len(categories) > 1:
                                product.sub_category = categories[1]
                            if len(categories) > 2:
                                product.product_family = categories[2]
                        
                        # Add to company's products
                        company.products.append(product)
                        
                        # Update global stats
                        global_stats.product_data["found"] += 1
                        if product.images:
                            global_stats.product_data["images"] += len(product.images)
                        if product.description:
                            global_stats.product_data["descriptions"] += 1
                    
                    # Small delay between product page requests
                    time.sleep(0.3)
            
            # If categories found, update global stats
            if categories:
                global_stats.product_data["categories"] += len(categories)
                
        except Exception as e:
            stack_trace = traceback.format_exc()
            log_repository.log_error(
                url, extraction_id, "ProductExtractionError", 
                f"Error extracting product info: {str(e)}", 
                stack_trace
            )
    
    def find_products_page(self, content: str, base_url: str) -> Optional[str]:
        """Find products page URL"""
        # Look for products section link
        products_link_patterns = [
            r'<a[^>]*\bhref="([^"]*products[^"]*)"',
            r'<a[^>]*\bhref="([^"]*catalogue[^"]*)"',
            r'<a[^>]*\bhref="([^"]*catalog[^"]*)"',
            r'<a[^>]*\bhref="([^"]*shop[^"]*)"'
        ]
        
        for pattern in products_link_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return self.resolve_url(match.group(1), base_url)
        
        return None
    
    def extract_product_from_page(self, content: str, url: str, company: CompanyEntity) -> None:
        """Extract product information from current page"""
        try:
            # Look for product sections directly on the page
            product_section_patterns = [
                r'<(?:div|section)[^>]*\b(?:id|class)="[^"]*\b(?:product|item)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section)>',
                r'<h\d[^>]*>\s*(?:Products|Our Products|Featured Products)\s*<\/h\d>([\s\S]*?)(?:<h\d|<\/div|<\/section)'
            ]
            
            for pattern in product_section_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    product_data = self.extract_product_details(match.group(1), url)
                    
                    if product_data.get("product_name"):
                        product = ProductEntity()
                        product.product_name = product_data["product_name"]
                        product.product_url = url
                        product.description = product_data.get("description", "")
                        product.price = product_data.get("price", "")
                        product.quantity = product_data.get("quantity", "")
                        product.specifications = product_data.get("specifications", "")
                        product.images = product_data.get("images", [])
                        
                        company.products.append(product)
                        
                        # Update global stats
                        global_stats.product_data["found"] += 1
                        if product.images:
                            global_stats.product_data["images"] += len(product.images)
                        if product.description:
                            global_stats.product_data["descriptions"] += 1
                        
                        break
        except Exception as e:
            log_repository.log_error(
                url, "unknown", "ProductFromPageError", 
                f"Error extracting product from page: {str(e)}"
            )
    
    def process_product_page(self, url: str) -> Optional[Dict[str, Any]]:
        """Process a product page"""
        # Avoid revisiting URLs
        if url in self.visited_urls:
            return None
        
        self.visited_urls.add(url)
        
        try:
            # Fetch the product page
            response = requests.get(
                url, 
                headers=self.headers,
                timeout=self.config.get("TIMEOUT_SECONDS", 30)
            )
            
            if response.status_code != 200:
                return None
            
            content = response.text
            
            # Extract product details
            return self.extract_product_details(content, url)
            
        except Exception as e:
            log_repository.log_error(
                url, "unknown", "ProductPageProcessError", 
                f"Error processing product page: {str(e)}"
            )
            return None
    
    def extract_product_links(self, content: str, base_url: str) -> List[Dict[str, str]]:
        """Extract product links from HTML content"""
        product_links = []
        
        try:
            # Look for links in product sections
            product_section_patterns = [
                r'<(?:div|section|ul)[^>]*\b(?:id|class)="[^"]*\b(?:product|item|listing|catalog|shop)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section|ul)>'
            ]
            
            product_sections = []
            
            # Extract product sections
            for pattern in product_section_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    product_sections.append(match.group(1))
            
            # If no dedicated product sections found, use the whole content
            if not product_sections:
                product_sections = [content]
            
            # Extract links from product sections
            for section in product_sections:
                link_pattern = r'<a\s+[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>'
                
                matches = re.finditer(link_pattern, section, re.IGNORECASE)
                for match in matches:
                    href = match.group(1)
                    text = self.clean_html(match.group(2)).strip()
                    
                    # Skip empty links, non-product links, or navigation links
                    if (not href or href == "#" or href.startswith("javascript:") or 
                        "login" in href or "cart" in href or 
                        "account" in href or "contact" in href):
                        continue
                    
                    # Skip links without text content
                    if not text:
                        continue
                    
                    # Resolve relative URL
                    full_url = self.resolve_url(href, base_url)
                    
                    # Only include links from the same domain
                    if (self.is_same_domain(full_url, base_url) and 
                        not self.is_excluded_path(full_url) and 
                        self.is_likely_product_link(full_url, text)):
                        
                        product_links.append({
                            "url": full_url,
                            "text": text
                        })
                        
                        # Limit to maximum products
                        if len(product_links) >= self.max_products:
                            break
            
            return product_links
            
        except Exception as e:
            log_repository.log_error(
                base_url, "unknown", "ProductLinksError", 
                f"Error extracting product links: {str(e)}"
            )
            return []
    
    def extract_categories(self, content: str) -> List[str]:
        """Extract categories from HTML content"""
        try:
            categories = []
            
            # Try to extract from breadcrumbs
            breadcrumb_patterns = [
                r'<(?:nav|div|ul)[^>]*\b(?:id|class)="[^"]*\b(?:breadcrumb|path|navigation)[^"]*"[^>]*>([\s\S]*?)<\/(?:nav|div|ul)>',
                r'<ol[^>]*\b(?:id|class)="[^"]*\b(?:breadcrumb)[^"]*"[^>]*>([\s\S]*?)<\/ol>'
            ]
            
            for pattern in breadcrumb_patterns:
                breadcrumb_match = re.search(pattern, content, re.IGNORECASE)
                if breadcrumb_match:
                    breadcrumb_content = breadcrumb_match.group(1)
                    link_pattern = r'<a[^>]*>([\s\S]*?)<\/a>'
                    
                    matches = re.finditer(link_pattern, breadcrumb_content, re.IGNORECASE)
                    for match in matches:
                        text = self.clean_html(match.group(1)).strip()
                        
                        # Skip "Home", "Index", etc.
                        if text and text.lower() not in ["home", "index", "main", "start"]:
                            categories.append(text)
                    
                    if categories:
                        break  # Found categories in breadcrumbs
            
            return categories
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "unknown", "CategoriesError", 
                f"Error extracting categories: {str(e)}"
            )
            return []
    
    def extract_product_details(self, content: str, url: str) -> Dict[str, Any]:
        """Extract product details from HTML content"""
        try:
            product_data = {
                "product_name": "",
                "description": "",
                "price": "",
                "quantity": "",
                "specifications": "",
                "images": []
            }
            
            # Extract product name (prioritize structured data)
            structured_data = self.extract_structured_data(content)
            if structured_data and 'product' in structured_data and 'name' in structured_data['product']:
                product_data["product_name"] = structured_data['product']['name']
            else:
                # Try common product name patterns
                product_name_patterns = [
                    r'<h1[^>]*\b(?:id|class)="[^"]*\b(?:product|item|title)[^"]*"[^>]*>([\s\S]*?)<\/h1>',
                    r'<h1[^>]*>([\s\S]*?)<\/h1>',
                    r'<div[^>]*\b(?:id|class)="[^"]*\b(?:product|item)[^"]*-title"[^>]*>([\s\S]*?)<\/div>'
                ]
                
                for pattern in product_name_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        product_data["product_name"] = self.clean_html(match.group(1)).strip()
                        break
                
                # If still no name, use page title as fallback
                if not product_data["product_name"]:
                    title_match = re.search(r'<title>(.*?)<\/title>', content, re.IGNORECASE)
                    if title_match:
                        title = title_match.group(1).strip()
                        # Get first part of title before separator
                        parts = re.split(r'\s*[|—-]\s*', title)
                        if parts:
                            product_data["product_name"] = parts[0].strip()
            
            # Extract product price
            if structured_data and 'product' in structured_data and 'offers' in structured_data['product'] and 'price' in structured_data['product']['offers']:
                product_data["price"] = structured_data['product']['offers']['price']
            else:
                # Try common price patterns
                price_patterns = [
                    r'<(?:div|span)[^>]*\b(?:id|class)="[^"]*\b(?:price|product-price)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|span)>',
                    r'<meta[^>]*\bitemprop="price"[^>]*\bcontent="([^"]*)">',
                    r'[$€£¥]\s*\d+(?:\.\d{1,2})?',
                    r'\d+(?:\.\d{1,2})?\s*[$€£¥]'
                ]
                
                for pattern in price_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        price = match.group(1) if len(match.groups()) > 0 else match.group(0)
                        product_data["price"] = self.clean_html(price).strip()
                        break
            
            # Extract product description
            if structured_data and 'product' in structured_data and 'description' in structured_data['product']:
                product_data["description"] = structured_data['product']['description']
            else:
                # Try common description patterns
                description_patterns = [
                    r'<(?:div|section)[^>]*\b(?:id|class)="[^"]*\b(?:product|item)[^"]*-description[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section)>',
                    r'<(?:div|section)[^>]*\b(?:id|class)="[^"]*\b(?:description)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section)>',
                    r'<div[^>]*\bitemprop="description"[^>]*>([\s\S]*?)<\/div>',
                    r'<meta[^>]*\bname="description"[^>]*\bcontent="([^"]*)">'
                ]
                
                for pattern in description_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        desc = match.group(1)
                        product_data["description"] = self.clean_html(desc).strip()
                        break
            
            # Extract product quantity/size information
            quantity_patterns = [
                r'<(?:div|span)[^>]*\b(?:id|class)="[^"]*\b(?:size|quantity|volume|weight|dimension)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|span)>',
                r'<span[^>]*\bitemprop="size"[^>]*>([\s\S]*?)<\/span>',
                r'<select[^>]*\b(?:id|name)="[^"]*\b(?:size|quantity|volume|weight)[^"]*"[^>]*>([\s\S]*?)<\/select>',
                r'(\d+(?:\.\d+)?\s*(?:ml|l|g|kg|oz|lb|pack|piece|count|ct))'
            ]
            
            for pattern in quantity_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    qty = match.group(1)
                    product_data["quantity"] = self.clean_html(qty).strip()
                    break
            
            # Extract product specifications
            spec_patterns = [
                r'<(?:div|section|table)[^>]*\b(?:id|class)="[^"]*\b(?:specification|technical|details|specs)[^"]*"[^>]*>([\s\S]*?)<\/(?:div|section|table)>',
                r'<(?:div|section)[^>]*\bitemprop="additionalProperty"[^>]*>([\s\S]*?)<\/(?:div|section)>',
                r'<h\d[^>]*>\s*(?:Specifications|Technical Details|Tech Specs|Additional Information)\s*<\/h\d>([\s\S]*?)(?:<h\d|<\/div|<\/section)',
                r'<table[^>]*\b(?:id|class)="[^"]*\b(?:product|item)[^"]*-attributes"[^>]*>([\s\S]*?)<\/table>'
            ]
            
            for pattern in spec_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    specs = match.group(1)
                    product_data["specifications"] = self.clean_html(specs).strip()
                    break
            
            # Extract product images
            if structured_data and 'product' in structured_data and 'image' in structured_data['product']:
                images = structured_data['product']['image']
                if isinstance(images, list):
                    product_data["images"] = [self.resolve_url(img, url) for img in images]
                else:
                    product_data["images"] = [self.resolve_url(images, url)]
            else:
                # Try common image patterns
                image_patterns = [
                    r'<img[^>]*\b(?:id|class)="[^"]*\b(?:product|item)[^"]*-image[^"]*"[^>]*src="([^"]*)"',
                    r'<div[^>]*\b(?:id|class)="[^"]*\b(?:product|item)[^"]*-gallery[^"]*"[^>]*>[\s\S]*?<img[^>]*src="([^"]*)"',
                    r'<a[^>]*\b(?:id|class|rel)="[^"]*\b(?:lightbox|gallery)[^"]*"[^>]*href="([^"]*)"',
                    r'<meta[^>]*\bproperty="og:image"[^>]*\bcontent="([^"]*)"'
                ]
                
                for pattern in image_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        img_url = self.resolve_url(match.group(1), url)
                        if img_url not in product_data["images"]:
                            product_data["images"].append(img_url)
                
                # If no product-specific images found, look for any image that might be a product image
                if not product_data["images"]:
                    any_image_pattern = r'<img[^>]*src="([^"]*)"[^>]*>'
                    
                    matches = re.finditer(any_image_pattern, content, re.IGNORECASE)
                    for match in matches:
                        src = match.group(1)
                        
                        # Skip tiny images, icons, logos, etc.
                        if ("icon" in src or "logo" in src or "banner" in src or 
                            "pixel" in src or src.endswith(".svg")):
                            continue
                        
                        # Resolve relative URL
                        image_url = self.resolve_url(src, url)
                        if image_url not in product_data["images"]:
                            product_data["images"].append(image_url)
                        
                        # Limit to a reasonable number of images
                        if len(product_data["images"]) >= 5:
                            break
            
            return product_data
            
        except Exception as e:
            log_repository.log_error(
                url, "unknown", "ProductDetailsError", 
                f"Error extracting product details: {str(e)}"
            )
            return {
                "product_name": "",
                "description": "",
                "price": "",
                "quantity": "",
                "specifications": "",
                "images": []
            }
    
    def is_excluded_path(self, url: str) -> bool:
        """Check if URL path should be excluded"""
        try:
            excluded_paths = [
                'about', 'contact', 'privacy', 'terms', 'faq', 'help', 'support',
                'blog', 'news', 'login', 'register', 'account', 'cart', 'checkout',
                'search', 'sitemap', 'careers', 'jobs', 'press', 'media'
            ]
            
            parsed_url = urlparse(url)
            path = parsed_url.path.lower()
            
            return any(
                path == f'/{excluded}' or 
                path == f'/{excluded}/' or 
                f'/{excluded}/' in path 
                for excluded in excluded_paths
            )
        except Exception:
            return False
    
    def is_same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs are from the same domain"""
        try:
            domain1 = urlparse(url1).netloc
            domain2 = urlparse(url2).netloc
            
            # Compare domains (ignore www. prefix)
            domain1 = domain1.replace('www.', '')
            domain2 = domain2.replace('www.', '')
            
            return domain1 == domain2
        except Exception:
            return False
    
    def is_likely_product_link(self, url: str, text: str) -> bool:
        """Check if a link is likely a product link"""
        try:
            # Check URL for product-related terms
            product_terms_in_url = [
                'product', 'item', 'shop', 'buy', 'purchase', 'catalog', 'catalogue',
                'collection', 'goods', 'merchandise', 'sale', 'order', 'category'
            ]
            
            parsed_url = urlparse(url)
            url_lower = url.lower()
            path_lower = parsed_url.path.lower()
            
            has_product_term_in_url = any(
                term in url_lower or term in path_lower 
                for term in product_terms_in_url
            )
            
            # Check if URL has product ID pattern
            has_product_id_pattern = bool(re.search(
                r'/p/|/product/|/item/|/prod[_-]?id/|/sku/|/id/\d+', 
                path_lower
            ))
            
            # Check text for product indicators
            text_lower = text.lower()
            has_product_indicator_in_text = (
                'buy' in text_lower or 
                'shop' in text_lower or 
                'view' in text_lower or
                'details' in text_lower or
                'more' in text_lower
            )
            
            # Check if link text is concise (likely product name) and not navigational
            is_concise_text = (
                text and 
                len(text) < 50 and 
                'about' not in text_lower and 
                'contact' not in text_lower and
                'home' not in text_lower
            )
            
            return (has_product_term_in_url or 
                    has_product_id_pattern or 
                    has_product_indicator_in_text or 
                    is_concise_text)
        except Exception:
            return False
