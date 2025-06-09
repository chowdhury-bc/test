import boto3
import psycopg2
from psycopg2 import pool
import os
import threading
from typing import Optional, Dict, Any
from contextlib import contextmanager
import time
from src.logging_config import app_logger

class ConnectionPoolManager:
    """Manages connection pools for databases and AWS services"""
    
    def __init__(self):
        self._db_pool = None
        self._boto3_session = None
        self._bedrock_client = None
        self._bedrock_agent_client = None
        self._pool_lock = threading.Lock()
        self._client_lock = threading.Lock()
        self._initialize_pools()
    
    def _initialize_pools(self):
        """Initialize all connection pools"""
        self._initialize_db_pool()
        self._initialize_aws_clients()
    
    def _initialize_db_pool(self):
        """Initialize PostgreSQL connection pool"""
        try:
            db_config = {
                "host": os.getenv("DB_HOST", "localhost"),
                "port": int(os.getenv("DB_PORT", "5432")),
                "database": os.getenv("DB_NAME", "websites"),
                "user": os.getenv("DB_USER", "postgres"),
                "password": os.getenv("DB_PASSWORD", ""),
            }
            
            # Try to create connection pool even with default localhost settings
            # This allows for local development scenarios
            try:
                self._db_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=int(os.getenv("DB_POOL_MIN_CONNECTIONS", "2")),
                    maxconn=int(os.getenv("DB_POOL_MAX_CONNECTIONS", "10")),
                    **db_config
                )
                app_logger.info("Database connection pool initialized successfully")
            except psycopg2.OperationalError as e:
                app_logger.warning(f"Database pool initialization failed: {str(e)}")
                app_logger.info("Database pool not available - continuing without database functionality")
                self._db_pool = None
                
        except Exception as e:
            app_logger.error(f"Failed to initialize database pool: {str(e)}")
            self._db_pool = None
    
    def _initialize_aws_clients(self):
        """Initialize AWS clients with connection pooling"""
        try:
            # Create a session with connection pooling
            self._boto3_session = boto3.Session(
                region_name=os.getenv("AWS_REGION", "us-east-1")
            )
            
            # Configure boto3 for connection pooling
            config = boto3.session.Config(
                region_name=os.getenv("AWS_REGION", "us-east-1"),
                retries={
                    'max_attempts': 3,
                    'mode': 'adaptive'
                },
                max_pool_connections=50,  # Increase pool size
                tcp_keepalive=True
            )
            
            # Create reusable clients
            self._bedrock_client = self._boto3_session.client(
                "bedrock-runtime", 
                config=config
            )
            self._bedrock_agent_client = self._boto3_session.client(
                "bedrock-agent-runtime", 
                config=config
            )
            
            app_logger.info("AWS client pool initialized")
            
        except Exception as e:
            app_logger.error(f"Failed to initialize AWS clients: {str(e)}")
            self._bedrock_client = None
            self._bedrock_agent_client = None
    
    @contextmanager
    def get_db_connection(self):
        """Get a database connection from the pool"""
        if not self._db_pool:
            raise Exception("Database pool not available")
        
        connection = None
        try:
            with self._pool_lock:
                connection = self._db_pool.getconn()
            
            if connection:
                # Test the connection
                if connection.closed:
                    raise psycopg2.OperationalError("Connection is closed")
                
                yield connection
            else:
                raise Exception("Could not get connection from pool")
                
        except Exception as e:
            app_logger.error(f"Database connection error: {str(e)}")
            # Try to rollback if there's an active transaction
            if connection and not connection.closed:
                try:
                    connection.rollback()
                except:
                    pass
            raise
        finally:
            # Return connection to pool
            if connection and self._db_pool:
                try:
                    with self._pool_lock:
                        self._db_pool.putconn(connection)
                except Exception as e:
                    app_logger.error(f"Error returning connection to pool: {str(e)}")
    
    def get_bedrock_client(self):
        """Get Bedrock client"""
        with self._client_lock:
            if not self._bedrock_client:
                self._initialize_aws_clients()
            return self._bedrock_client
    
    def get_bedrock_agent_client(self):
        """Get Bedrock Agent client"""
        with self._client_lock:
            if not self._bedrock_agent_client:
                self._initialize_aws_clients()
            return self._bedrock_agent_client
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        stats = {
            "db_pool_available": False,
            "aws_clients_available": False,
            "timestamp": time.time()
        }
        
        try:
            if self._db_pool:
                # Note: ThreadedConnectionPool doesn't expose detailed stats
                # but we can check if it's functioning
                stats["db_pool_available"] = True
                stats["db_pool_status"] = "healthy"
            else:
                stats["db_pool_status"] = "not_initialized"
                
        except Exception as e:
            stats["db_pool_status"] = f"error: {str(e)}"
        
        try:
            if self._bedrock_client and self._bedrock_agent_client:
                stats["aws_clients_available"] = True
                stats["aws_clients_status"] = "healthy"
            else:
                stats["aws_clients_status"] = "not_initialized"
                
        except Exception as e:
            stats["aws_clients_status"] = f"error: {str(e)}"
        
        return stats
    
    def health_check(self) -> Dict[str, bool]:
        """Perform health checks on all pools"""
        health = {
            "database": False,
            "bedrock": False,
            "bedrock_agent": False
        }
        
        # Test database pool
        if self._db_pool:
            try:
                with self.get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                    health["database"] = True
            except Exception as e:
                app_logger.error(f"Database health check failed: {str(e)}")
        
        # Test Bedrock clients
        try:
            if self._bedrock_client:
                # This is a simple check - you might want to make an actual API call
                health["bedrock"] = True
        except Exception as e:
            app_logger.error(f"Bedrock health check failed: {str(e)}")
        
        try:
            if self._bedrock_agent_client:
                health["bedrock_agent"] = True
        except Exception as e:
            app_logger.error(f"Bedrock Agent health check failed: {str(e)}")
        
        return health
    
    def close_all_pools(self):
        """Close all connection pools"""
        try:
            if self._db_pool:
                self._db_pool.closeall()
                app_logger.info("Database pool closed")
        except Exception as e:
            app_logger.error(f"Error closing database pool: {str(e)}")
        
        # AWS clients don't need explicit closing, but we can reset them
        self._bedrock_client = None
        self._bedrock_agent_client = None
        app_logger.info("AWS clients reset")

# Global connection pool instance
connection_pool = ConnectionPoolManager()

# Cleanup function for graceful shutdown
def cleanup_pools():
    """Cleanup function to be called on application shutdown"""
    connection_pool.close_all_pools()