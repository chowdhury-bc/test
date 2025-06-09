import asyncio
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import os
from src.cache_manager import cache_manager
from src.query_engine import get_contexts, answer_query
from src.agent import cached_detect_database_intent, cached_execute_database_intent, detect_database_intent, execute_database_intent
from src.logging_config import app_logger

class CacheWarmer:
    """Intelligent cache warming system to preload frequently accessed data"""
    
    def __init__(self):
        self.warming_stats = {
            "sessions_started": 0,
            "items_warmed": 0,
            "total_time": 0,
            "last_warming": None
        }
        
        # Common queries that should be pre-cached
        self.common_queries = [
            "What are the main causes of wildfires?",
            "How does climate change affect oil production?",
            "What are DOI environmental regulations?",
            "Tell me about renewable energy on federal lands",
            "What is the Bureau of Land Management?",
            "How many websites mention climate change?",
            "What are the statistics about the database?",
            "Show me websites about oil drilling",
            "Find pages about environmental protection"
        ]
        
        # Common database intents to warm
        self.common_db_intents = [
            {"type": "website_stats"},
            {"type": "website_count", "search_term": "oil"},
            {"type": "website_count", "search_term": "climate"},
            {"type": "website_count", "search_term": "energy"},
            {"type": "domain_search", "search_term": "usgs.gov"},
            {"type": "domain_search", "search_term": "doi.gov"}
        ]
    
    async def warm_cache_startup(self):
        """Warm cache during application startup"""
        start_time = time.time()
        self.warming_stats["sessions_started"] += 1
        
        app_logger.info("Starting cache warming process...")
        
        try:
            # Warm knowledge base queries
            await self._warm_knowledge_base_cache()
            
            # Warm database intent detection
            await self._warm_database_intent_cache()
            
            # Warm database queries
            await self._warm_database_query_cache()
            
            total_time = time.time() - start_time
            self.warming_stats["total_time"] += total_time
            self.warming_stats["last_warming"] = datetime.now().isoformat()
            
            app_logger.info(f"Cache warming completed in {total_time:.2f}s. "
                          f"Warmed {self.warming_stats['items_warmed']} items.")
            
        except Exception as e:
            app_logger.error(f"Error during cache warming: {str(e)}")
    
    async def _warm_knowledge_base_cache(self):
        """Warm knowledge base query cache"""
        app_logger.info("Warming knowledge base cache...")
        
        tasks = []
        for query in self.common_queries[:5]:  # Limit to avoid overloading
            if not query.startswith("How many") and not query.startswith("Show me"):
                tasks.append(self._warm_knowledge_query(query))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _warm_knowledge_query(self, query: str):
        """Warm a single knowledge base query"""
        try:
            # Check if already cached
            cache_key = cache_manager._generate_cache_key("get_contexts", query, None, 5)
            cached_result = cache_manager.get("knowledge_base", cache_key)
            
            if cached_result is None:
                # Not cached, so warm it
                await asyncio.get_event_loop().run_in_executor(
                    None, get_contexts, query
                )
                self.warming_stats["items_warmed"] += 1
                app_logger.debug(f"Warmed knowledge base query: {query[:30]}...")
            else:
                app_logger.debug(f"Knowledge base query already cached: {query[:30]}...")
                
        except Exception as e:
            app_logger.warning(f"Failed to warm knowledge query '{query[:30]}...': {str(e)}")
    
    async def _warm_database_intent_cache(self):
        """Warm database intent detection cache"""
        app_logger.info("Warming database intent cache...")
        
        for query in self.common_queries:
            try:
                # Check if already cached
                cache_key = cache_manager._generate_cache_key("detect_database_intent", query)
                cached_result = cache_manager.get("intent_detection", cache_key)
                
                if cached_result is None:
                    # Not cached, so warm it
                    await asyncio.get_event_loop().run_in_executor(
                        None, detect_database_intent, query
                    )
                    self.warming_stats["items_warmed"] += 1
                    app_logger.debug(f"Warmed intent detection: {query[:30]}...")
                    
            except Exception as e:
                app_logger.warning(f"Failed to warm intent detection '{query[:30]}...': {str(e)}")
    
    async def _warm_database_query_cache(self):
        """Warm database query cache"""
        app_logger.info("Warming database query cache...")
        
        for intent in self.common_db_intents:
            try:
                # Check if already cached
                cache_key = cache_manager._generate_cache_key("execute_database_intent", intent)
                cached_result = cache_manager.get("database_queries", cache_key)
                
                if cached_result is None:
                    # Not cached, so warm it
                    await asyncio.get_event_loop().run_in_executor(
                        None, execute_database_intent, intent
                    )
                    self.warming_stats["items_warmed"] += 1
                    app_logger.debug(f"Warmed database query: {intent}")
                    
            except Exception as e:
                app_logger.warning(f"Failed to warm database query {intent}: {str(e)}")
    
    def schedule_periodic_warming(self, interval_hours: int = 6):
        """Schedule periodic cache warming"""
        async def periodic_warmer():
            while True:
                try:
                    await asyncio.sleep(interval_hours * 3600)  # Convert hours to seconds
                    app_logger.info("Starting scheduled cache warming...")
                    await self.warm_cache_startup()
                except Exception as e:
                    app_logger.error(f"Error in periodic cache warming: {str(e)}")
        
        # Start the periodic warming task
        asyncio.create_task(periodic_warmer())
        app_logger.info(f"Scheduled periodic cache warming every {interval_hours} hours")
    
    def warm_user_query_pattern(self, query: str):
        """Warm cache based on user query patterns"""
        try:
            # Extract keywords from the query
            keywords = self._extract_keywords(query)
            
            # Generate related queries to warm
            related_queries = self._generate_related_queries(keywords)
            
            # Warm related queries in background
            asyncio.create_task(self._warm_related_queries(related_queries))
            
        except Exception as e:
            app_logger.warning(f"Failed to warm related queries for '{query}': {str(e)}")
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from a user query"""
        # Simple keyword extraction
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'what', 'how', 'when', 'where', 'why', 'who'
        }
        
        words = query.lower().split()
        keywords = [word.strip('.,!?;:') for word in words if word not in stop_words and len(word) > 2]
        return keywords[:5]  # Limit to 5 keywords
    
    def _generate_related_queries(self, keywords: List[str]) -> List[str]:
        """Generate related queries based on keywords"""
        related_queries = []
        
        for keyword in keywords:
            # Generate count queries
            related_queries.append(f"How many websites mention {keyword}?")
            # Generate search queries
            related_queries.append(f"Show me websites about {keyword}")
            
        return related_queries[:3]  # Limit to avoid overloading
    
    async def _warm_related_queries(self, queries: List[str]):
        """Warm related queries in background"""
        for query in queries:
            try:
                # Detect intent and warm if needed
                intent = detect_database_intent(query)
                if intent:
                    cache_key = cache_manager._generate_cache_key("execute_database_intent", intent)
                    cached_result = cache_manager.get("database_queries", cache_key)
                    
                    if cached_result is None:
                        await asyncio.get_event_loop().run_in_executor(
                            None, execute_database_intent, intent
                        )
                        app_logger.debug(f"Warmed related query: {query[:30]}...")
                        
            except Exception as e:
                app_logger.debug(f"Failed to warm related query '{query}': {str(e)}")
    
    def get_warming_stats(self) -> Dict[str, Any]:
        """Get cache warming statistics"""
        return {
            **self.warming_stats,
            "avg_warming_time": (
                self.warming_stats["total_time"] / 
                max(self.warming_stats["sessions_started"], 1)
            ),
            "cache_stats": cache_manager.get_stats()
        }
    
    def load_query_patterns_from_logs(self, log_file: Optional[str] = None) -> List[str]:
        """Load common query patterns from application logs"""
        if not log_file or not os.path.exists(log_file):
            return []
        
        queries = []
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                
            # Extract queries from log lines (simplified pattern matching)
            for line in lines[-1000:]:  # Last 1000 lines
                if "Query processed" in line or "query:" in line.lower():
                    # Extract query from log line (this would need customization based on log format)
                    # This is a simplified example
                    parts = line.split("query:")
                    if len(parts) > 1:
                        query = parts[1].strip().split()[0]  # First word after query:
                        if len(query) > 10:  # Filter out very short queries
                            queries.append(query)
            
            # Return unique queries, most recent first
            return list(dict.fromkeys(queries))[:20]
            
        except Exception as e:
            app_logger.warning(f"Failed to load query patterns from logs: {str(e)}")
            return []

# Global cache warmer instance
cache_warmer = CacheWarmer()

async def initialize_cache_warming():
    """Initialize cache warming on application startup"""
    try:
        await cache_warmer.warm_cache_startup()
        
        # Schedule periodic warming if in production
        if os.getenv("ENVIRONMENT", "development") == "production":
            cache_warmer.schedule_periodic_warming(interval_hours=6)
            
    except Exception as e:
        app_logger.error(f"Failed to initialize cache warming: {str(e)}")