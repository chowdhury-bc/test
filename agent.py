import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List, Optional
import os
import re
import time
from src.logging_config import app_logger
from src.cache_manager import cache_manager, cached
from src.connection_pool import connection_pool

def clean_text(text: str) -> str:
    """Clean text by removing invalid UTF-8 characters"""
    if not isinstance(text, str):
        return str(text)
    # Remove invalid UTF-8 characters
    return text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')

class WebsiteAgent:
    """Agent class to handle website search and database queries with connection pooling"""
    
    def __init__(self):
        """Initialize with connection pool manager"""
        self.stats = {"queries": 0, "cache_hits": 0, "errors": 0}
            
    @cached("database_queries", ttl=3600)  # Cache for 1 hour
    def search_websites(self, term: str) -> Dict[str, Any]:
        """Search websites for a specific term with context snippets and advanced caching"""
        start_time = time.time()
        self.stats["queries"] += 1
        
        try:
            # Check if database pool is available
            if not connection_pool._db_pool:
                app_logger.warning("Database pool not available for website search")
                return {
                    "success": False,
                    "error": "Database not available",
                    "count": 0,
                    "results": [],
                    "search_term": term
                }
            
            with connection_pool.get_db_connection() as conn:
                # Create a cursor that returns dictionaries
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Use parameterized query to prevent SQL injection with context snippets
                query = """
                    SELECT 
                        id, 
                        url, 
                        domain,
                        downloaded_at,
                        -- Extract a snippet of text around the match (100 chars before and after)
                        substring(content, 
                                greatest(1, position(lower(%s) in lower(content)) - 100), 
                                200 + length(%s)) AS context_snippet,
                        -- Count occurrences
                        (length(lower(content)) - length(replace(lower(content), lower(%s), ''))) / length(%s) AS occurrence_count
                    FROM websites
                    WHERE content ILIKE %s
                    ORDER BY occurrence_count DESC, downloaded_at DESC
                    LIMIT 50  -- Limit results for performance
                """
                
                # Count query
                count_query = """
                    SELECT COUNT(*) 
                    FROM discover_doi.websites 
                    WHERE content ILIKE %s
                """
                
                search_param = f"%{term}%"
                
                # Execute the search query
                cursor.execute(query, (term, term, term, term, search_param))
                results = cursor.fetchall()
                
                # Execute the count query
                cursor.execute(count_query, (search_param,))
                count_result = cursor.fetchone()
                total_count = count_result["count"] if count_result else 0
                
                cursor.close()
                
                processing_time = time.time() - start_time
                app_logger.info(f"Website search for '{term}' completed in {processing_time:.2f}s")
                
                return {
                    "success": True,
                    "count": total_count,
                    "results": list(results),
                    "search_term": term,
                    "processing_time": processing_time
                }
                
        except Exception as e:
            self.stats["errors"] += 1
            app_logger.error(f"Error searching websites: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "results": []
            }
    
    @cached("stats", ttl=1800)  # Cache stats for 30 minutes
    def get_stats(self) -> Dict[str, Any]:
        """Get general statistics about the website database with caching"""
        start_time = time.time()
        
        try:
            # Check if database pool is available
            if not connection_pool._db_pool:
                app_logger.warning("Database pool not available for stats")
                return {
                    "success": False,
                    "error": "Database not available"
                }
            
            with connection_pool.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                stats = {}
                
                # Get total website count
                cursor.execute("SELECT COUNT(*) as total FROM websites")
                result = cursor.fetchone()
                stats["total_websites"] = result["total"] if result else 0
                
                # Get domain statistics
                cursor.execute("""
                    SELECT domain, COUNT(*) as count 
                    FROM websites 
                    GROUP BY domain 
                    ORDER BY count DESC 
                    LIMIT 20
                """)
                stats["top_domains"] = cursor.fetchall()
                
                cursor.close()
                
                processing_time = time.time() - start_time
                app_logger.info(f"Database stats query completed in {processing_time:.2f}s")
                
                return {
                    "success": True,
                    "stats": stats,
                    "processing_time": processing_time
                }
                
        except Exception as e:
            self.stats["errors"] += 1
            app_logger.error(f"Error getting website stats: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def search_by_domain(self, domain: str) -> Dict[str, Any]:
        """Search websites for content mentioning a specific domain"""
        # Check if database pool is available
        if not connection_pool._db_pool:
            return {
                "success": False,
                "error": "Database not available",
                "count": 0,
                "results": []
            }
        
        try:
            with connection_pool.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Use parameterized query with context snippets and occurrence counting
                query = """
                    SELECT 
                        id, 
                        url, 
                        domain,
                        downloaded_at,
                        -- Extract a snippet of text around the match (100 chars before and after)
                        substring(content, 
                                greatest(1, position(lower(%s) in lower(content)) - 100), 
                                200 + length(%s)) AS context_snippet,
                        -- Count occurrences
                        (length(lower(content)) - length(replace(lower(content), lower(%s), ''))) / length(%s) AS occurrence_count
                    FROM websites
                    WHERE content ILIKE %s
                    ORDER BY occurrence_count DESC, downloaded_at DESC
                    LIMIT 20
                """
                
                # Count query
                count_query = """
                    SELECT COUNT(*) as total
                    FROM websites 
                    WHERE content ILIKE %s
                """
                
                search_param = f"%{domain}%"
                
                # Execute the search query
                cursor.execute(query, (domain, domain, domain, domain, search_param))
                results = cursor.fetchall()
                
                # Execute the count query
                cursor.execute(count_query, (search_param,))
                count_result = cursor.fetchone()
                total_count = count_result["total"] if count_result else 0
                
                # Get keyword stats from matching documents
                domain_stats = {}
                if total_count > 0:
                    # Only get keywords from documents that mention the domain
                    keyword_query = """
                        SELECT keywords 
                        FROM websites 
                        WHERE content ILIKE %s AND keywords IS NOT NULL
                    """
                    cursor.execute(keyword_query, (search_param,))
                    keywords_raw = cursor.fetchall()
                    
                    all_keywords = []
                    for row in keywords_raw:
                        if row["keywords"]:
                            all_keywords.extend([kw.strip() for kw in row["keywords"].split(',')])
                    
                    from collections import Counter
                    keyword_counts = Counter(all_keywords).most_common(5)
                    domain_stats["top_keywords"] = [{"keyword": kw, "count": count} for kw, count in keyword_counts]
                
                cursor.close()
                
                return {
                    "success": True,
                    "count": total_count,
                    "results": list(results),
                    "domain_stats": domain_stats,
                    "domain": domain
                }
                
        except Exception as e:
            app_logger.error(f"Error searching content for domain references: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "results": []
            }

    def search_by_link_domain(self, domain: str) -> Dict[str, Any]:
        """Search websites for pages that have href links to a specific domain"""
        # Check if database pool is available
        if not connection_pool._db_pool:
            return {
                "success": False,
                "error": "Database not available",
                "count": 0,
                "results": []
            }
        
        try:
            with connection_pool.get_db_connection() as conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Use a query to find pages with links to the specified domain
                query = """
                    SELECT 
                        id, 
                        url, 
                        domain,
                        downloaded_at,
                        -- Look for anchor tags with href containing the domain
                        regexp_matches(content, '<a[^>]*href=["''][^"'']*' || %s || '[^"'']*["''][^>]*>', 'gi') AS link_sample,
                        -- Count occurrences of such links
                        array_length(regexp_matches(content, '<a[^>]*href=["''][^"'']*' || %s || '[^"'']*["''][^>]*>', 'gi'), 1) AS link_count
                    FROM websites
                    WHERE content ~* ('<a[^>]*href=["''][^"'']*' || %s || '[^"'']*["''][^>]*>')
                    ORDER BY link_count DESC, downloaded_at DESC
                """
                
                # Count query
                count_query = """
                    SELECT COUNT(*) as total
                    FROM websites 
                    WHERE content ~* ('<a[^>]*href=["''][^"'']*' || %s || '[^"'']*["''][^>]*>')
                """
                
                # Execute the search query
                cursor.execute(query, (domain, domain, domain))
                results = cursor.fetchall()
                
                # Execute the count query
                cursor.execute(count_query, (domain,))
                count_result = cursor.fetchone()
                total_count = count_result["total"] if count_result else 0
                
                cursor.close()
                
                return {
                    "success": True,
                    "count": total_count,
                    "results": list(results),
                    "domain": domain
                }
                
        except Exception as e:
            app_logger.error(f"Error searching for link references: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "results": []
            }


def detect_database_intent(query: str) -> Optional[Dict[str, Any]]:
    """
    Detect if a user query requires database access and extract relevant parameters
    Returns None if no database intent is detected, or a dict with intent details
    """
    # Patterns for different types of queries
    patterns = {
        "count_websites": r"(?:how\s+many|count|number\s+of)\s+(?:websites?|pages?|sites?)\s+(?:have|contain|include|about|mention|discuss)\s+(?:the\s+(?:word|term|keyword|phrase)\s+)?['\"]?([^'\"]+?)['\"]?",
        "search_content": r"(?:find|search|show|list|get)\s+(?:websites?|pages?|sites?|content)\s+(?:that\s+)?(?:contain|include|have|about|mention|discuss|with)\s+(?:the\s+(?:word|term|keyword|phrase)\s+)?['\"]?([^'\"]+?)['\"]?",
        "find_links": r"(?:find|show|list|get)\s+(?:websites?|pages?|sites?)\s+(?:that\s+)?(?:have|contain|include|with)\s+(?:links?\s+to|hrefs?\s+to|references?\s+to)\s+['\"]?([^'\"]+?)['\"]?",
        "list_websites": r"(?:list|show|get)\s+(?:all\s+)?(?:websites?|domains?|sites?)",
        "website_stats": r"(?:statistics|stats|info|information)\s+(?:about|on|for)\s+(?:the\s+)?(?:websites?|pages?|database)"
    }
    
    # Check each pattern
    for intent_type, pattern in patterns.items():
        match = re.search(pattern, query.lower())
        if match:
            # For patterns that extract a search term
            if intent_type in ["count_websites", "search_content", "find_links"]:
                groups = [g for g in match.groups() if g]
                if groups:
                    search_term = groups[0].strip()
                    return {
                        "type": intent_type,
                        "search_term": search_term
                    }
            # For patterns without extraction
            elif intent_type in ["list_websites", "website_stats"]:
                return {
                    "type": intent_type
                }
    
    return None


def execute_database_intent(intent: Dict) -> Any:
    """Execute database queries using the websites table only"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        # Get database connection
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', 5432),
            options=f"-c search_path={os.getenv('DB_NAME')}",
        )
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Log the intent for debugging
        app_logger.info(f"Executing database intent: {intent}")
        
        # Build query based on intent type
        query = ""
        params = []
        
        if intent["type"] == "count_websites":
            search_term = intent.get("search_term", "")
            query = """
                SELECT COUNT(*) as count
                FROM websites 
                WHERE content ILIKE %s
            """
            params = [f"%{search_term}%"]
                
        elif intent["type"] == "search_content":
            search_term = intent.get("search_term", "")
            query = """
                SELECT 
                    url, 
                    domain,
                    downloaded_at,
                    -- Extract a snippet of text around the match
                    substring(content, 
                            greatest(1, position(lower(%s) in lower(content)) - 100), 
                            300) AS context_snippet,
                    -- Count occurrences
                    (length(lower(content)) - length(replace(lower(content), lower(%s), ''))) / length(%s) AS occurrence_count
                FROM websites 
                WHERE content ILIKE %s
                ORDER BY occurrence_count DESC, downloaded_at DESC
                LIMIT 10
            """
            params = [search_term, search_term, search_term, f"%{search_term}%"]
            
        elif intent["type"] == "find_links":
            link_pattern = intent.get("search_term", "")
            query = """
                SELECT 
                    url, 
                    domain,
                    downloaded_at,
                    -- Extract HTML snippets containing the links
                    substring(content FROM '.*<a[^>]*href[^>]*' || %s || '[^>]*>.*') AS link_context
                FROM websites 
                WHERE content ~* ('<a[^>]*href[^>]*' || %s || '[^>]*>')
                ORDER BY downloaded_at DESC
                LIMIT 10
            """
            params = [link_pattern, link_pattern]
            
        elif intent["type"] == "list_websites":
            query = """
                SELECT 
                    domain,
                    COUNT(*) as page_count,
                    MAX(downloaded_at) as last_updated
                FROM websites 
                WHERE domain IS NOT NULL
                GROUP BY domain
                ORDER BY page_count DESC
                LIMIT 20
            """
            
        elif intent["type"] == "website_stats":
            query = """
                SELECT 
                    COUNT(*) as total_websites,
                    COUNT(DISTINCT domain) as unique_domains,
                    AVG(length(content)) as avg_content_length,
                    MAX(downloaded_at) as last_download
                FROM websites
            """
            
        else:
            # Default fallback query
            query = "SELECT COUNT(*) as total_records FROM websites"
        
        # Log the actual SQL query for debugging
        app_logger.info(f"Executing SQL query: {query}")
        app_logger.info(f"Query parameters: {params}")
        
        # Execute query
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Fetch results
        results = cursor.fetchall()
        
        # Convert to list of dictionaries
        result_list = []
        for row in results:
            if isinstance(row, dict):
                result_list.append(dict(row))
            else:
                # Handle other row types
                result_list.append(dict(row))
        
        cursor.close()
        conn.close()
        
        app_logger.info(f"Database query successful, returned {len(result_list)} rows")
        app_logger.info(f"Sample result: {result_list[0] if result_list else 'No results'}")
        
        return result_list
        
    except psycopg2.Error as e:
        app_logger.error(f"PostgreSQL error: {str(e)}")
        app_logger.error(f"Error code: {e.pgcode}")
        app_logger.error(f"SQL State: {e.pgerror if hasattr(e, 'pgerror') else 'N/A'}")
        return {"error": f"Database query failed: {str(e)}"}
    except Exception as e:
        app_logger.error(f"General error executing database intent: {str(e)}")
        import traceback
        app_logger.error(f"Traceback: {traceback.format_exc()}")
        return {"error": f"Query execution failed: {str(e)}"}


def format_database_response(intent_type: str, db_result: Any) -> str:
    """Format database results for display with better error handling"""
    
    app_logger.info(f"Formatting database response for intent: {intent_type}")
    app_logger.info(f"Database result type: {type(db_result)}")
    
    try:
        # Handle error results
        if isinstance(db_result, dict) and "error" in db_result:
            return f"I'm sorry, I encountered an error while searching the database: {db_result['error']}"
        
        # Handle empty results
        if not db_result or (isinstance(db_result, list) and len(db_result) == 0):
            return "No results found for your query."
        
        # Format based on intent type
        if intent_type == "count_websites":
            if isinstance(db_result, list) and len(db_result) > 0:
                count = db_result[0].get('count', 0)
                return f"I found {count} websites containing your search term."
            else:
                return "Unable to count websites from the results."
                
        elif intent_type == "search_content":
            if isinstance(db_result, list):
                if len(db_result) == 0:
                    return "No content found matching your search terms."
                
                response = f"I found {len(db_result)} websites with relevant content:\n\n"
                for i, result in enumerate(db_result, 1):
                    url = result.get('url', 'No URL')
                    domain = result.get('domain', 'Unknown domain')
                    context = result.get('context_snippet', 'No context available')
                    occurrences = result.get('occurrence_count', 0)
                    
                    # Clean up HTML from context snippet
                    import re
                    clean_context = re.sub(r'<[^>]+>', '', str(context))[:200] + "..."
                    
                    response += f"{i}. **{domain}**\n"
                    response += f"   URL: {url}\n"
                    response += f"   Occurrences: {occurrences}\n"
                    response += f"   Context: {clean_context}\n\n"
                
                return response
            else:
                return "Search completed but results are in an unexpected format."
                
        elif intent_type == "find_links":
            if isinstance(db_result, list):
                if len(db_result) == 0:
                    return "No pages found with the specified links."
                
                response = f"I found {len(db_result)} websites with matching links:\n\n"
                for i, result in enumerate(db_result, 1):
                    url = result.get('url', 'No URL')
                    domain = result.get('domain', 'Unknown domain')
                    response += f"{i}. **{domain}**\n   URL: {url}\n\n"
                
                return response
            else:
                return "Link search completed but results are in an unexpected format."
                
        elif intent_type == "list_websites":
            if isinstance(db_result, list):
                if len(db_result) == 0:
                    return "No websites found in the database."
                
                response = f"Here are the top {len(db_result)} websites by page count:\n\n"
                for i, result in enumerate(db_result, 1):
                    domain = result.get('domain', 'Unknown domain')
                    page_count = result.get('page_count', 0)
                    last_updated = result.get('last_updated', 'Unknown')
                    response += f"{i}. **{domain}** - {page_count} pages (last updated: {last_updated})\n"
                
                return response
            else:
                return "Website listing completed but results are in an unexpected format."
                
        elif intent_type == "website_stats":
            if isinstance(db_result, list) and len(db_result) > 0:
                stats = db_result[0]
                total = stats.get('total_websites', 0)
                domains = stats.get('unique_domains', 0)
                avg_length = stats.get('avg_content_length', 0)
                last_download = stats.get('last_download', 'Unknown')
                
                response = f"Website Database Statistics:\n\n"
                response += f"- Total websites: {total}\n"
                response += f"- Unique domains: {domains}\n"
                response += f"- Average content length: {avg_length:,.0f} characters\n"
                response += f"- Last download: {last_download}\n"
                
                return response
            else:
                return "Unable to retrieve database statistics."
        
        # Default formatting for unknown intent types
        return f"Query completed successfully. Found {len(db_result) if isinstance(db_result, list) else 1} result(s)."
        
    except Exception as e:
        app_logger.error(f"Error formatting database response: {str(e)}")
        import traceback
        app_logger.error(f"Traceback: {traceback.format_exc()}")
        return f"I completed the database query but encountered an error while formatting the results: {str(e)}"