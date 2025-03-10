"""
Data Repository for Web Stryker R7 Python Edition
Handles data storage and retrieval for extraction results
"""
import os
import json
import csv
import sqlite3
import datetime
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from domain_models import CompanyEntity, ProductEntity
from config import config
from logging_system import log_repository


class DataRepository:
    """Manages data storage and retrieval for extraction results"""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize data repository"""
        self.db_path = db_path or config.get("DATABASE.CONNECTION_STRING", "web_stryker.db")
        self._setup_database()
    
    def _setup_database(self) -> None:
        """Set up database tables if they don't exist"""
        try:
            # Ensure directory exists for the database file
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            os.makedirs(db_dir, exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create companies table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    company_name TEXT,
                    company_description TEXT,
                    company_type TEXT,
                    emails TEXT,
                    phones TEXT,
                    addresses TEXT,
                    logo TEXT,
                    extraction_date TEXT,
                    status TEXT DEFAULT 'Completed'
                )
            ''')
            
            # Create products table with foreign key to companies
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    product_name TEXT,
                    product_url TEXT,
                    main_category TEXT,
                    sub_category TEXT,
                    product_family TEXT,
                    price TEXT,
                    quantity TEXT,
                    description TEXT,
                    specifications TEXT,
                    images TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
                )
            ''')
            
            # Create index on company URL
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_company_url ON companies (url)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "setup", "DatabaseSetupError", 
                f"Error setting up database: {str(e)}"
            )
    
    def store_company(self, company: Union[CompanyEntity, Dict[str, Any]]) -> int:
        """Store company data in database
        
        Args:
            company: Company entity or dictionary with company data
            
        Returns:
            Company ID in database
        """
        try:
            # Convert CompanyEntity to dict if needed
            company_data = company.to_dict() if isinstance(company, CompanyEntity) else company
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if company with this URL already exists
            cursor.execute('SELECT id FROM companies WHERE url = ?', (company_data.get('url'),))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing company
                company_id = existing[0]
                
                cursor.execute('''
                    UPDATE companies SET
                        company_name = ?,
                        company_description = ?,
                        company_type = ?,
                        emails = ?,
                        phones = ?,
                        addresses = ?,
                        logo = ?,
                        extraction_date = ?,
                        status = ?
                    WHERE id = ?
                ''', (
                    company_data.get('company_name', ''),
                    company_data.get('company_description', ''),
                    company_data.get('company_type', ''),
                    company_data.get('emails', ''),
                    company_data.get('phones', ''),
                    company_data.get('addresses', ''),
                    company_data.get('logo', ''),
                    company_data.get('extraction_date', datetime.datetime.now().isoformat()),
                    company_data.get('status', 'Completed'),
                    company_id
                ))
                
                # Delete existing products for this company
                cursor.execute('DELETE FROM products WHERE company_id = ?', (company_id,))
                
            else:
                # Insert new company
                cursor.execute('''
                    INSERT INTO companies (
                        url, company_name, company_description, company_type,
                        emails, phones, addresses, logo, extraction_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    company_data.get('url', ''),
                    company_data.get('company_name', ''),
                    company_data.get('company_description', ''),
                    company_data.get('company_type', ''),
                    company_data.get('emails', ''),
                    company_data.get('phones', ''),
                    company_data.get('addresses', ''),
                    company_data.get('logo', ''),
                    company_data.get('extraction_date', datetime.datetime.now().isoformat()),
                    company_data.get('status', 'Completed')
                ))
                
                company_id = cursor.lastrowid
                
            # Store products if available in original CompanyEntity
            if isinstance(company, CompanyEntity) and company.products:
                for product in company.products:
                    self._store_product(cursor, company_id, product)
            
            conn.commit()
            conn.close()
            
            return company_id
            
        except Exception as e:
            log_repository.log_error(
                company_data.get('url', 'unknown') if 'url' in company_data else 'unknown',
                "store", "DatabaseStoreError", 
                f"Error storing company data: {str(e)}"
            )
            return -1
    
    def _store_product(self, cursor, company_id: int, product: Union[ProductEntity, Dict[str, Any]]) -> None:
        """Store product data in database"""
        try:
            # Convert ProductEntity to dict if needed
            product_data = product.to_dict() if isinstance(product, ProductEntity) else product
            
            cursor.execute('''
                INSERT INTO products (
                    company_id, product_name, product_url, main_category, sub_category,
                    product_family, price, quantity, description, specifications, images
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                company_id,
                product_data.get('product_name', ''),
                product_data.get('product_url', ''),
                product_data.get('main_category', ''),
                product_data.get('sub_category', ''),
                product_data.get('product_family', ''),
                product_data.get('price', ''),
                product_data.get('quantity', ''),
                product_data.get('description', ''),
                product_data.get('specifications', ''),
                ','.join(product_data.get('images', []))
            ))
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "store", "DatabaseStoreProductError", 
                f"Error storing product data: {str(e)}"
            )
    
    def update_status(self, url: str, status: str) -> bool:
        """Update extraction status for a URL
        
        Args:
            url: The URL to update
            status: New status (Completed, Failed, In Progress)
            
        Returns:
            Success status
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'UPDATE companies SET status = ? WHERE url = ?',
                (status, url)
            )
            
            if cursor.rowcount == 0:
                # URL not found, insert a new record with this status
                cursor.execute(
                    'INSERT INTO companies (url, status, extraction_date) VALUES (?, ?, ?)',
                    (url, status, datetime.datetime.now().isoformat())
                )
            
            conn.commit()
            conn.close()
            
            return True
            
        except Exception as e:
            log_repository.log_error(
                url, "update", "DatabaseUpdateError", 
                f"Error updating status: {str(e)}"
            )
            return False
    
    def get_company(self, url: str) -> Optional[Dict[str, Any]]:
        """Get company data by URL
        
        Args:
            url: Company URL
            
        Returns:
            Company data dictionary or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.cursor()
            
            # Get company data
            cursor.execute(
                'SELECT * FROM companies WHERE url = ?',
                (url,)
            )
            
            company_row = cursor.fetchone()
            if not company_row:
                conn.close()
                return None
            
            company_data = dict(company_row)
            
            # Get products for this company
            cursor.execute(
                'SELECT * FROM products WHERE company_id = ?',
                (company_data['id'],)
            )
            
            products = [dict(row) for row in cursor.fetchall()]
            company_data['products'] = products
            
            conn.close()
            
            return company_data
            
        except Exception as e:
            log_repository.log_error(
                url, "get", "DatabaseGetError", 
                f"Error getting company data: {str(e)}"
            )
            return None
    
    def get_recent_extractions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent extractions
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of company data dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                '''
                SELECT c.*, 
                       (SELECT p.product_name FROM products p 
                        WHERE p.company_id = c.id 
                        ORDER BY p.id LIMIT 1) as primary_product_name
                FROM companies c
                ORDER BY extraction_date DESC
                LIMIT ?
                ''',
                (limit,)
            )
            
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return results
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "get", "DatabaseGetRecentError", 
                f"Error getting recent extractions: {str(e)}"
            )
            return []
    
    def search_companies(self, query: Dict[str, Any] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Search for companies based on query parameters
        
        Args:
            query: Dictionary of search parameters
            limit: Maximum number of results
            
        Returns:
            List of matching company data dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            sql_query = '''
                SELECT c.*, 
                       (SELECT p.product_name FROM products p 
                        WHERE p.company_id = c.id 
                        ORDER BY p.id LIMIT 1) as primary_product_name
                FROM companies c
            '''
            
            conditions = []
            params = []
            
            # Build query conditions
            if query:
                if 'company_name' in query and query['company_name']:
                    conditions.append('c.company_name LIKE ?')
                    params.append(f"%{query['company_name']}%")
                
                if 'company_type' in query and query['company_type']:
                    conditions.append('c.company_type LIKE ?')
                    params.append(f"%{query['company_type']}%")
                
                if 'status' in query and query['status']:
                    conditions.append('c.status = ?')
                    params.append(query['status'])
                
                if 'date_from' in query and query['date_from']:
                    conditions.append('c.extraction_date >= ?')
                    params.append(query['date_from'])
                
                if 'date_to' in query and query['date_to']:
                    conditions.append('c.extraction_date <= ?')
                    params.append(query['date_to'])
                
                if 'has_email' in query and query['has_email']:
                    conditions.append('c.emails != ""')
                
                if 'has_products' in query and query['has_products']:
                    conditions.append('EXISTS (SELECT 1 FROM products p WHERE p.company_id = c.id)')
                
            # Add conditions to query
            if conditions:
                sql_query += ' WHERE ' + ' AND '.join(conditions)
            
            # Add limit
            sql_query += ' ORDER BY c.extraction_date DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(sql_query, params)
            
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return results
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "search", "DatabaseSearchError", 
                f"Error searching companies: {str(e)}"
            )
            return []
    
    def export_to_csv(self, file_path: str, query: Dict[str, Any] = None) -> bool:
        """Export extraction data to CSV file
        
        Args:
            file_path: Path to save CSV file
            query: Optional search parameters
            
        Returns:
            Success status
        """
        try:
            # Get companies to export
            companies = self.search_companies(query, limit=1000)  # limit to 1000 for performance
            
            if not companies:
                return False
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # Define CSV headers
            headers = [
                'URL', 'Company Name', 'Company Type', 'Emails', 'Phones', 
                'Addresses', 'Company Description', 'Extraction Date', 'Status',
                'Product Name', 'Product URL', 'Product Category', 'Price'
            ]
            
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                for company in companies:
                    # Get products for this company
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    cursor.execute(
                        'SELECT * FROM products WHERE company_id = ?',
                        (company['id'],)
                    )
                    
                    products = [dict(row) for row in cursor.fetchall()]
                    conn.close()
                    
                    if products:
                        # Write one row per product
                        for product in products:
                            writer.writerow([
                                company.get('url', ''),
                                company.get('company_name', ''),
                                company.get('company_type', ''),
                                company.get('emails', ''),
                                company.get('phones', ''),
                                company.get('addresses', ''),
                                company.get('company_description', '')[:500],  # limit description length
                                company.get('extraction_date', ''),
                                company.get('status', ''),
                                product.get('product_name', ''),
                                product.get('product_url', ''),
                                product.get('main_category', ''),
                                product.get('price', '')
                            ])
                    else:
                        # Write one row for company without products
                        writer.writerow([
                            company.get('url', ''),
                            company.get('company_name', ''),
                            company.get('company_type', ''),
                            company.get('emails', ''),
                            company.get('phones', ''),
                            company.get('addresses', ''),
                            company.get('company_description', '')[:500],  # limit description length
                            company.get('extraction_date', ''),
                            company.get('status', ''),
                            '', '', '', ''  # empty product fields
                        ])
            
            return True
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "export", "CSVExportError", 
                f"Error exporting to CSV: {str(e)}"
            )
            return False
    
    def export_to_json(self, file_path: str, query: Dict[str, Any] = None) -> bool:
        """Export extraction data to JSON file
        
        Args:
            file_path: Path to save JSON file
            query: Optional search parameters
            
        Returns:
            Success status
        """
        try:
            # Get companies to export
            companies = self.search_companies(query, limit=1000)  # limit to 1000 for performance
            
            if not companies:
                return False
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # For each company, get its products
            result_data = []
            
            for company in companies:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(
                    'SELECT * FROM products WHERE company_id = ?',
                    (company['id'],)
                )
                
                products = [dict(row) for row in cursor.fetchall()]
                conn.close()
                
                # Add products to company data
                company_data = dict(company)
                company_data['products'] = products
                
                # Remove database ID
                if 'id' in company_data:
                    del company_data['id']
                
                for product in company_data['products']:
                    if 'id' in product:
                        del product['id']
                    if 'company_id' in product:
                        del product['company_id']
                
                result_data.append(company_data)
            
            # Write to JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            log_repository.log_error(
                "unknown", "export", "JSONExportError", 
                f"Error exporting to JSON: {str(e)}"
            )
            return False


# Create singleton instance
data_repository = DataRepository()
