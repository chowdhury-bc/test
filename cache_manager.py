import redis
import redis.asyncio as aioredis
import json
import pickle
import hashlib
import os
from typing import Any, Optional, Dict, List
from functools import wraps
import asyncio
from datetime import datetime, timedelta
from src.logging_config import app_logger

class CacheManager:    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self.async_redis_client = None
        self.fallback_cache = {}  # In-memory fallback
        self.cache_stats = {"hits": 0, "misses": 0, "errors": 0}
        
        # Cache TTL settings (in seconds)
        self.ttl_settings = {
            "knowledge_base": 86400,    # 24 hours for knowledge base queries
            "database_queries": 3600,   # 1 hour for database queries  
            "intent_detection": 7200,   # 2 hours for intent detection
            "responses": 21600,         # 6 hours for formatted responses
            "stats": 1800,              # 30 minutes for stats
        }
        
        self._initialize_redis()
    
    def _initialize_redis(self):
        """Initialize Redis connection with fallback to in-memory cache"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self.redis_client.ping()
            app_logger.info("Redis cache initialized successfully")
        except Exception as e:
            app_logger.warning(f"Redis not available, using in-memory fallback: {str(e)}")
            self.redis_client = None
    
    async def _initialize_async_redis(self):
        """Initialize async Redis connection"""
        if not self.async_redis_client:
            try:
                self.async_redis_client = await aioredis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                await self.async_redis_client.ping()
                app_logger.info("Async Redis cache initialized successfully")
            except Exception as e:
                app_logger.warning(f"Async Redis not available: {str(e)}")
                self.async_redis_client = None
    
    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a consistent cache key from arguments"""
        # Create a string representation of all arguments
        key_data = f"{prefix}:{str(args)}:{str(sorted(kwargs.items()))}"
        # Hash to create a consistent key
        return f"doi_chat:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    def _serialize_data(self, data: Any) -> str:
        """Serialize data for storage"""
        try:
            # Try JSON first (faster)
            return json.dumps(data, default=str)
        except (TypeError, ValueError):
            # Fall back to pickle for complex objects
            return pickle.dumps(data).decode('latin1')
    
    def _deserialize_data(self, data: str) -> Any:
        """Deserialize data from storage"""
        try:
            # Try JSON first
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            # Fall back to pickle
            return pickle.loads(data.encode('latin1'))
    
    def get(self, cache_type: str, key: str, default=None) -> Any:
        """Get item from cache"""
        cache_key = f"{cache_type}:{key}"
        
        try:
            if self.redis_client:
                result = self.redis_client.get(cache_key)
                if result is not None:
                    self.cache_stats["hits"] += 1
                    return self._deserialize_data(result)
            else:
                # Fallback to in-memory cache
                if cache_key in self.fallback_cache:
                    entry = self.fallback_cache[cache_key]
                    if entry["expires"] > datetime.now():
                        self.cache_stats["hits"] += 1
                        return entry["data"]
                    else:
                        del self.fallback_cache[cache_key]
            
            self.cache_stats["misses"] += 1
            return default
            
        except Exception as e:
            app_logger.error(f"Cache get error: {str(e)}")
            self.cache_stats["errors"] += 1
            return default
    
    def set(self, cache_type: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set item in cache"""
        cache_key = f"{cache_type}:{key}"
        ttl = ttl or self.ttl_settings.get(cache_type, 3600)
        
        try:
            serialized_value = self._serialize_data(value)
            
            if self.redis_client:
                self.redis_client.setex(cache_key, ttl, serialized_value)
            else:
                # Fallback to in-memory cache
                self.fallback_cache[cache_key] = {
                    "data": value,
                    "expires": datetime.now() + timedelta(seconds=ttl)
                }
                # Simple cleanup of expired entries
                self._cleanup_memory_cache()
            
            return True
            
        except Exception as e:
            app_logger.error(f"Cache set error: {str(e)}")
            self.cache_stats["errors"] += 1
            return False
    
    async def get_async(self, cache_type: str, key: str, default=None) -> Any:
        """Async get item from cache"""
        if not self.async_redis_client:
            await self._initialize_async_redis()
        
        cache_key = f"{cache_type}:{key}"
        
        try:
            if self.async_redis_client:
                result = await self.async_redis_client.get(cache_key)
                if result is not None:
                    self.cache_stats["hits"] += 1
                    return self._deserialize_data(result)
            
            self.cache_stats["misses"] += 1
            return default
            
        except Exception as e:
            app_logger.error(f"Async cache get error: {str(e)}")
            self.cache_stats["errors"] += 1
            return default
    
    async def set_async(self, cache_type: str, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Async set item in cache"""
        if not self.async_redis_client:
            await self._initialize_async_redis()
        
        cache_key = f"{cache_type}:{key}"
        ttl = ttl or self.ttl_settings.get(cache_type, 3600)
        
        try:
            if self.async_redis_client:
                serialized_value = self._serialize_data(value)
                await self.async_redis_client.setex(cache_key, ttl, serialized_value)
                return True
            
            return False
            
        except Exception as e:
            app_logger.error(f"Async cache set error: {str(e)}")
            self.cache_stats["errors"] += 1
            return False
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern"""
        try:
            if self.redis_client:
                keys = self.redis_client.keys(f"*{pattern}*")
                if keys:
                    return self.redis_client.delete(*keys)
            else:
                # Fallback cleanup for memory cache
                keys_to_delete = [k for k in self.fallback_cache.keys() if pattern in k]
                for key in keys_to_delete:
                    del self.fallback_cache[key]
                return len(keys_to_delete)
            
            return 0
            
        except Exception as e:
            app_logger.error(f"Cache invalidation error: {str(e)}")
            return 0
    
    def _cleanup_memory_cache(self):
        """Clean up expired entries from memory cache"""
        if len(self.fallback_cache) > 1000:  # Limit memory usage
            now = datetime.now()
            expired_keys = [
                key for key, entry in self.fallback_cache.items() 
                if entry["expires"] <= now
            ]
            for key in expired_keys:
                del self.fallback_cache[key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        stats = {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "errors": self.cache_stats["errors"],
            "hit_rate": f"{hit_rate:.1f}%",
            "backend": "redis" if self.redis_client else "memory",
            "total_requests": total_requests
        }
        
        # Add Redis-specific stats if available
        if self.redis_client:
            try:
                redis_info = self.redis_client.info("memory")
                stats["redis_memory_mb"] = round(redis_info.get("used_memory", 0) / 1024 / 1024, 2)
                stats["redis_keys"] = self.redis_client.dbsize()
            except:
                pass
        else:
            stats["memory_cache_size"] = len(self.fallback_cache)
        
        return stats
    
    def clear_all(self) -> bool:
        """Clear all cache entries"""
        try:
            if self.redis_client:
                keys = self.redis_client.keys("doi_chat:*")
                if keys:
                    self.redis_client.delete(*keys)
            else:
                self.fallback_cache.clear()
            
            self.cache_stats = {"hits": 0, "misses": 0, "errors": 0}
            app_logger.info("Cache cleared successfully")
            return True
            
        except Exception as e:
            app_logger.error(f"Cache clear error: {str(e)}")
            return False

# Global cache instance
cache_manager = CacheManager()

def cached(cache_type: str, ttl: Optional[int] = None, key_func=None):
    """Decorator for caching function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache_manager._generate_cache_key(func.__name__, *args, **kwargs)
            
            # Try to get from cache
            result = cache_manager.get(cache_type, cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_type, cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator

def async_cached(cache_type: str, ttl: Optional[int] = None, key_func=None):
    """Decorator for caching async function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = cache_manager._generate_cache_key(func.__name__, *args, **kwargs)
            
            # Try to get from cache
            result = await cache_manager.get_async(cache_type, cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set_async(cache_type, cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator