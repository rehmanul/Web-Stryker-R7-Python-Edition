"""
Domain models for Web Stryker R7 Python Edition
Implements core domain entities for extraction system
"""
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ProductEntity:
    """Domain model for product data"""
    product_name: str = ""
    product_url: str = ""
    main_category: str = ""
    sub_category: str = ""
    product_family: str = ""
    price: str = ""
    quantity: str = ""
    description: str = ""
    specifications: str = ""
    images: List[str] = field(default_factory=list)
    
    def is_valid(self) -> bool:
        """Check if product has valid essential data"""
        return bool(self.product_name or self.product_url)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "product_name": self.product_name,
            "product_url": self.product_url,
            "main_category": self.main_category,
            "sub_category": self.sub_category,
            "product_family": self.product_family,
            "price": self.price,
            "quantity": self.quantity,
            "description": self.description,
            "specifications": self.specifications,
            "images": self.images
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProductEntity':
        """Create from dictionary"""
        return cls(
            product_name=data.get("product_name", ""),
            product_url=data.get("product_url", ""),
            main_category=data.get("main_category", ""),
            sub_category=data.get("sub_category", ""),
            product_family=data.get("product_family", ""),
            price=data.get("price", ""),
            quantity=data.get("quantity", ""),
            description=data.get("description", ""),
            specifications=data.get("specifications", ""),
            images=data.get("images", [])
        )


@dataclass
class CompanyEntity:
    """Domain model for company data"""
    url: str = ""
    company_name: str = ""
    company_description: str = ""
    company_type: str = ""
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    addresses: List[str] = field(default_factory=list)
    extraction_date: str = ""
    products: List[ProductEntity] = field(default_factory=list)
    logo: str = ""
    
    def __post_init__(self):
        """Set extraction date if not provided"""
        if not self.extraction_date:
            self.extraction_date = datetime.now().isoformat()
    
    def is_valid(self) -> bool:
        """Check if company has valid essential data"""
        return bool(self.company_name and self.url)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        # Get the primary product if available
        primary_product = self.products[0] if self.products else None
        
        result = {
            "url": self.url,
            "company_name": self.company_name,
            "company_description": self.company_description,
            "company_type": self.company_type,
            "emails": ", ".join(self.emails) if self.emails else "",
            "phones": ", ".join(self.phones) if self.phones else "",
            "addresses": "; ".join(self.addresses) if self.addresses else "",
            "extraction_date": self.extraction_date,
            
            # Product information (from primary product or empty)
            "product_name": primary_product.product_name if primary_product else "",
            "product_url": primary_product.product_url if primary_product else "",
            "product_category": primary_product.main_category if primary_product else "",
            "product_subcategory": primary_product.sub_category if primary_product else "",
            "product_family": primary_product.product_family if primary_product else "",
            "quantity": primary_product.quantity if primary_product else "",
            "price": primary_product.price if primary_product else "",
            "product_description": primary_product.description if primary_product else "",
            "specifications": primary_product.specifications if primary_product else "",
            "images": ", ".join(primary_product.images) if primary_product and primary_product.images else ""
        }
        
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        company_dict = self.to_dict()
        # Add products list for full serialization
        company_dict["all_products"] = [p.to_dict() for p in self.products]
        return json.dumps(company_dict, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompanyEntity':
        """Create from dictionary"""
        company = cls(
            url=data.get("url", ""),
            company_name=data.get("company_name", ""),
            company_description=data.get("company_description", ""),
            company_type=data.get("company_type", ""),
            emails=data.get("emails", "").split(", ") if data.get("emails") else [],
            phones=data.get("phones", "").split(", ") if data.get("phones") else [],
            addresses=data.get("addresses", "").split("; ") if data.get("addresses") else [],
            extraction_date=data.get("extraction_date", datetime.now().isoformat()),
            logo=data.get("logo", "")
        )
        
        # Handle products if present
        if "all_products" in data and isinstance(data["all_products"], list):
            company.products = [ProductEntity.from_dict(p) for p in data["all_products"]]
        
        return company


class ExtractionState:
    """Manages extraction state and progress"""
    # Class-level dictionary to track all extraction states
    _extraction_states: Dict[str, Dict[str, Any]] = {}
    
    def __init__(self, extraction_id: str, url: str):
        """Initialize extraction state"""
        self.extraction_id = extraction_id
        
        # Initialize in global tracking object
        ExtractionState._extraction_states[extraction_id] = {
            "paused": False,
            "stopped": False,
            "url": url,
            "start_time": datetime.now().isoformat(),
            "progress": 0,
            "stage": "Initializing"
        }
    
    def update_progress(self, progress: int, stage: str) -> None:
        """Update progress information"""
        if not self.extraction_id or self.extraction_id not in ExtractionState._extraction_states:
            return
        
        ExtractionState._extraction_states[self.extraction_id]["progress"] = progress
        ExtractionState._extraction_states[self.extraction_id]["stage"] = stage
    
    @classmethod
    def is_stopped(cls, extraction_id: str) -> bool:
        """Check if extraction is stopped"""
        return (extraction_id and 
                extraction_id in cls._extraction_states and 
                cls._extraction_states[extraction_id]["stopped"])
    
    @classmethod
    def is_paused(cls, extraction_id: str) -> bool:
        """Check if extraction is paused"""
        return (extraction_id and 
                extraction_id in cls._extraction_states and 
                cls._extraction_states[extraction_id]["paused"])
    
    @classmethod
    def pause(cls, extraction_id: str) -> None:
        """Pause extraction"""
        if extraction_id in cls._extraction_states:
            cls._extraction_states[extraction_id]["paused"] = True
    
    @classmethod
    def resume(cls, extraction_id: str) -> None:
        """Resume extraction"""
        if extraction_id in cls._extraction_states:
            cls._extraction_states[extraction_id]["paused"] = False
    
    @classmethod
    def stop(cls, extraction_id: str) -> None:
        """Stop extraction"""
        if extraction_id in cls._extraction_states:
            cls._extraction_states[extraction_id]["stopped"] = True
    
    @classmethod
    def get_state(cls, extraction_id: str) -> Optional[Dict[str, Any]]:
        """Get extraction state"""
        if extraction_id in cls._extraction_states:
            return cls._extraction_states[extraction_id]
        return None
    
    def cleanup(self) -> None:
        """Clean up extraction state"""
        if self.extraction_id in ExtractionState._extraction_states:
            del ExtractionState._extraction_states[self.extraction_id]


# Global statistics for tracking and reporting
class GlobalStats:
    """Tracks global statistics for all extractions"""
    
    def __init__(self):
        self.processed = 0
        self.remaining = 0
        self.success = 0
        self.fail = 0
        self.api_calls = {
            "azure": {"success": 0, "fail": 0},
            "knowledge_graph": {"success": 0, "fail": 0},
            "google_cloud": {"success": 0, "fail": 0}
        }
        self.company_data = {
            "found": 0,
            "emails": 0, 
            "phones": 0,
            "addresses": 0,
            "descriptions": 0,
            "types": 0
        }
        self.product_data = {
            "found": 0,
            "images": 0,
            "descriptions": 0,
            "categories": 0
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reporting"""
        return {
            "processed": self.processed,
            "remaining": self.remaining,
            "success": self.success,
            "fail": self.fail,
            "api_calls": self.api_calls,
            "company_data": self.company_data,
            "product_data": self.product_data
        }
    
    def reset(self) -> None:
        """Reset all statistics"""
        self.__init__()


# Create global stats instance
global_stats = GlobalStats()
