"""
Logging System for Web Stryker R7 Python Edition
Handles logging operations and error tracking
"""
import os
import time
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
from functools import wraps

# Configure logging
logs_dir = Path("logs")
os.makedirs(logs_dir, exist_ok=True)

# Create loggers
main_logger = logging.getLogger("web_stryker")
main_logger.setLevel(logging.INFO)

extraction_logger = logging.getLogger("extraction")
extraction_logger.setLevel(logging.INFO)

error_logger = logging.getLogger("error")
error_logger.setLevel(logging.ERROR)

# Create formatters
standard_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create file handlers
main_file_handler = logging.FileHandler(logs_dir / "web_stryker.log")
main_file_handler.setFormatter(standard_formatter)
main_logger.addHandler(main_file_handler)

extraction_file_handler = logging.FileHandler(logs_dir / "extraction.log")
extraction_file_handler.setFormatter(standard_formatter)
extraction_logger.addHandler(extraction_file_handler)

error_file_handler = logging.FileHandler(logs_dir / "error.log")
error_file_handler.setFormatter(standard_formatter)
error_logger.addHandler(error_file_handler)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(standard_formatter)
main_logger.addHandler(console_handler)


class LogRepository:
    """Handles logging operations and provides methods for querying logs"""
    
    def __init__(self, db_path: str = "logs/extraction_logs.db"):
        """Initialize log repository with database connection"""
        self.db_path = db_path
        self._setup_db()
    
    def _setup_db(self) -> None:
        """Setup database tables for logging if they don't exist"""
        import sqlite3
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create extraction log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS extraction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                url TEXT,
                extraction_id TEXT,
                operation TEXT,
                status TEXT,
                details TEXT,
                duration INTEGER
            )
        ''')
        
        # Create error log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                url TEXT,
                extraction_id TEXT,
                error_type TEXT,
                error_message TEXT,
                stack_trace TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def log_operation(self, url: str, extraction_id: str, operation: str, 
                      status: str, details: str, duration: Optional[int] = None) -> None:
        """Log extraction operation to the database and logs"""
        # Log to file
        extraction_logger.info(
            f"[{extraction_id}] [{operation}] {status}: {details} "
            f"{'(' + str(duration) + 'ms)' if duration else ''}"
        )
        
        # Log to database
        try:
            import sqlite3
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            cursor.execute(
                "INSERT INTO extraction_log (timestamp, url, extraction_id, operation, status, details, duration) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (timestamp, url, extraction_id, operation, status, details, duration)
            )
            
            conn.commit()
            conn.close()
        except Exception as e:
            error_logger.error(f"Failed to log operation to database: {e}")
    
    def log_error(self, url: str, extraction_id: str, error_type: str, 
                  error_message: str, stack_trace: Optional[str] = None) -> None:
        """Log error to the database and logs"""
        # Log to file
        error_logger.error(
            f"[{extraction_id}] [{error_type}] {error_message}"
        )
        
        # Log to database
        try:
            import sqlite3
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            cursor.execute(
                "INSERT INTO error_log (timestamp, url, extraction_id, error_type, error_message, stack_trace) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (timestamp, url, extraction_id, error_type, error_message, stack_trace)
            )
            
            conn.commit()
            conn.close()
        except Exception as e:
            error_logger.error(f"Failed to log error to database: {e}")
    
    def get_recent_operations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent operations from the database"""
        try:
            import sqlite3
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM extraction_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return results
        except Exception as e:
            error_logger.error(f"Failed to get recent operations: {e}")
            return []
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent errors from the database"""
        try:
            import sqlite3
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM error_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return results
        except Exception as e:
            error_logger.error(f"Failed to get recent errors: {e}")
            return []
    
    def time_and_log_operation(self, url: str, extraction_id: str, operation: str, 
                              func: Callable, *args, **kwargs) -> Any:
        """Measure execution time of a function and log the result"""
        start_time = time.time()
        result = None
        status = "Success"
        details = "Operation completed successfully"
        
        try:
            # Execute the function
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            # Log the error
            status = "Error"
            details = str(e)
            stack_trace = traceback.format_exc()
            self.log_error(url, extraction_id, "OperationError", str(e), stack_trace)
            raise
        finally:
            # Calculate duration and log the operation
            end_time = time.time()
            duration_ms = int((end_time - start_time) * 1000)
            self.log_operation(url, extraction_id, operation, status, details, duration_ms)


def log_execution_time(logger=main_logger):
    """Decorator to log function execution time"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                execution_time = time.time() - start_time
                logger.info(f"{func.__name__} executed in {execution_time:.2f}s")
        return wrapper
    return decorator


# Create singleton instance
log_repository = LogRepository()
