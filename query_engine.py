import boto3
import json
from dotenv import load_dotenv
import os
import asyncio
import aiohttp
import concurrent.futures
from functools import lru_cache
from typing import List, Dict, Any, Tuple
import hashlib
import time

from src.cache_manager import cache_manager, cached, async_cached
from src.connection_pool import connection_pool
from src.logging_config import app_logger

load_dotenv()

KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")

# Configuration options
DEFAULT_RESULTS_LIMIT = 5
MAX_CONTEXT_LENGTH = 1500

def _generate_query_hash(query: str, limit: int) -> str:
    """Generate a consistent hash for query caching"""
    query_string = f"{query}:{limit}:{KNOWLEDGE_BASE_ID}"
    return hashlib.md5(query_string.encode()).hexdigest()

def _clean_text(text: str) -> str:
    """Clean text by removing invalid UTF-8 characters and surrogates"""
    if not isinstance(text, str):
        return str(text)
    
    # First, remove or replace surrogate characters
    import re
    # Remove surrogates (unpaired high/low surrogates)
    text = re.sub(r'[\ud800-\udfff]', '', text)
    
    # Remove other problematic Unicode characters
    text = ''.join(char for char in text if ord(char) < 0x110000 and not (0xD800 <= ord(char) <= 0xDFFF))
    
    # Remove invalid UTF-8 characters by encoding and decoding with errors='ignore'
    text = text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    
    # Additional cleaning for common problematic characters
    text = text.replace('\ufffd', '')  # Remove replacement characters
    text = text.replace('\x00', '')   # Remove null characters
    
    return text

@cached("knowledge_base", ttl=86400)  # Cache for 24 hours
def get_contexts(query, kbase_id=KNOWLEDGE_BASE_ID, limit=DEFAULT_RESULTS_LIMIT):
    """
    This function takes a query, knowledge base id, and number of results as input, 
    and returns the contexts for the query.
    Uses advanced caching to improve response time for similar queries.
    
    :param query: Natural language query from the user
    :param kbase_id: Knowledge base ID from .env file
    :param limit: Number of results to return (reduced default)
    :return: The contexts for the query
    """
    start_time = time.time()
    
    try:
        # Use connection pool for Bedrock agent client
        bedrock_agent_client = connection_pool.get_bedrock_agent_client()
        
        # Getting the contexts for the query from the knowledge base
        results = bedrock_agent_client.retrieve(
            retrievalQuery={"text": query},
            knowledgeBaseId=kbase_id,
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": limit}},
        )
        
        app_logger.info(f"Knowledge base query completed in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        app_logger.error(f"Knowledge base retrieval error: {str(e)}")
        return []
    
    contexts = []
    for retrieved_result in results["retrievalResults"]:
        # Limit the length of each context to reduce token count
        # Extract text content for the main context
        text = _clean_text(retrieved_result["content"]["text"])
        
        # Debugging - uncomment to print full structure of retrieved_result
        # print(f"Retrieved result structure: {json.dumps(retrieved_result, indent=2)}")
        
        # Access other potentially useful fields (if needed)
        # - Score represents the relevance of this result
        score = retrieved_result.get("score", 0)
        # - Metadata may contain additional document properties
        metadata = retrieved_result.get("metadata", {})
        
        # Extract top 3 lines from the document
        top_lines = _clean_text("\n".join(text.strip().split('\n')[:3]))
        
        # Extract a snippet for relevant text (around 150 chars for display)
        snippet = _clean_text(text[:150] + "..." if len(text) > 150 else text)
            
        contexts.append({
            "text": text,
            "snippet": snippet,
            "top_lines": top_lines,
            "document_reference": _clean_text(retrieved_result["location"]["s3Location"]["uri"]),
        })
    
    return contexts

@cached("responses", ttl=21600)  # Cache responses for 6 hours
def answer_query(query, conversation_history=None):
    """
    Takes a user query, retrieves relevant context from the knowledge base,
    and generates a response using AWS Bedrock models with improved caching
    
    :param query: The user's question
    :param conversation_history: List of previous {role, content} message pairs
    :return: tuple containing (response_text, references_list)
    """
    start_time = time.time()
    
    try:
        # Get contexts from knowledge base (this is already cached)
        retrieved_contexts = get_contexts(query)
        
        # Extract just the text and references
        context_texts = [context["text"] for context in retrieved_contexts]
        
        # Create references with source, top lines, and snippet information
        references = [
            {
                "source": context["document_reference"],
                "top_lines": context["top_lines"],
                "snippet": context["snippet"] 
            } 
            for context in retrieved_contexts
        ]
        
        # Join contexts into a single string
        context_string = "\n\n".join(context_texts)
        
        # Initialize messages with system prompt (optional)
        messages = []
        
        # Add conversation history if provided (limit to recent messages)
        if conversation_history:
            # Limit conversation history to prevent token overflow
            recent_history = conversation_history[-6:]  # Last 6 messages
            messages.extend(recent_history)
        
        # Add current query with context
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Based on the following documents, please provide a detailed and accurate answer to this question: {query}\n\n{context_string}\n\nAnswer the question based only on the information provided above. If you're unsure or the information isn't in the provided documents, say so."
                }
            ]
        })
        
        # Use connection pool for Bedrock client
        bedrock_client = connection_pool.get_bedrock_client()
        
        # Call the Bedrock model using Messages API format
        response = bedrock_client.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": messages,
                "temperature": 0.7
            }),
            contentType="application/json",
        )
        
        # Extract the generated text from the response
        response_body = json.loads(response["body"].read())
        response_text = _clean_text(response_body["content"][0]["text"])
        
        processing_time = time.time() - start_time
        app_logger.info(f"Answer query completed in {processing_time:.2f}s")
        
        return response_text, references
        
    except Exception as e:
        app_logger.error(f"Error in answer_query: {str(e)}")
        return f"I'm sorry, I encountered an error processing your request: {str(e)}", []

@async_cached("knowledge_base", ttl=86400)
async def get_contexts_async(query, kbase_id=KNOWLEDGE_BASE_ID, limit=DEFAULT_RESULTS_LIMIT):
    """
    Async version of get_contexts with improved caching
    """
    start_time = time.time()
    
    try:
        # Run the synchronous operation in a thread pool
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Use connection pool for Bedrock agent client
            bedrock_agent_client = connection_pool.get_bedrock_agent_client()
            
            # Execute the retrieval in a thread
            results = await loop.run_in_executor(
                executor, 
                lambda: bedrock_agent_client.retrieve(
                    retrievalQuery={"text": query},
                    knowledgeBaseId=kbase_id,
                    retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": limit}},
                )
            )
            
        app_logger.info(f"Async knowledge base query completed in {time.time() - start_time:.2f}s")
        
        contexts = []
        for retrieved_result in results["retrievalResults"]:
            text = _clean_text(retrieved_result["content"]["text"])
            score = retrieved_result.get("score", 0)
            metadata = retrieved_result.get("metadata", {})
            
            top_lines = _clean_text("\n".join(text.strip().split('\n')[:3]))
            snippet = _clean_text(text[:150] + "..." if len(text) > 150 else text)
                
            contexts.append({
                "text": text,
                "snippet": snippet,
                "top_lines": top_lines,
                "document_reference": _clean_text(retrieved_result["location"]["s3Location"]["uri"]),
            })
        
        return contexts
        
    except Exception as e:
        app_logger.error(f"Async knowledge base retrieval error: {str(e)}")
        return []

@async_cached("responses", ttl=21600)
async def answer_query_async(query, conversation_history=None):
    """
    Fully asynchronous version of answer_query function with advanced caching
    
    :param query: The user's question
    :param conversation_history: List of previous message pairs
    :return: tuple containing (response_text, references_list)
    """
    start_time = time.time()
    
    try:
        # Get contexts from knowledge base asynchronously
        retrieved_contexts = await get_contexts_async(query)
        
        # Extract just the text and references
        context_texts = [context["text"] for context in retrieved_contexts]
        
        # Create references with source, top lines, and snippet information
        references = [
            {
                "source": context["document_reference"],
                "top_lines": context["top_lines"],
                "snippet": context["snippet"] 
            } 
            for context in retrieved_contexts
        ]
        
        # Join contexts into a single string
        context_string = "\n\n".join(context_texts)
        
        # Initialize messages
        messages = []
        
        # Add conversation history if provided (limit to recent messages)
        if conversation_history:
            recent_history = conversation_history[-6:]  # Last 6 messages
            messages.extend(recent_history)
        
        # Add current query with context
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Based on the following documents, please provide a detailed and accurate answer to this question: {query}\n\n{context_string}\n\nAnswer the question based only on the information provided above. If you're unsure or the information isn't in the provided documents, say so."
                }
            ]
        })
        
        # Run the Bedrock call in a thread pool
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            bedrock_client = connection_pool.get_bedrock_client()
            
            response = await loop.run_in_executor(
                executor,
                lambda: bedrock_client.invoke_model(
                    modelId=MODEL_ID,
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": messages,
                        "temperature": 0.7
                    }),
                    contentType="application/json",
                )
            )
        
        # Extract the generated text from the response
        response_body = json.loads(response["body"].read())
        response_text = _clean_text(response_body["content"][0]["text"])
        
        processing_time = time.time() - start_time
        app_logger.info(f"Async answer query completed in {processing_time:.2f}s")
        
        return response_text, references
        
    except Exception as e:
        app_logger.error(f"Error in async answer_query: {str(e)}")
        return f"I'm sorry, I encountered an error processing your request: {str(e)}", []

# Batch processing functions for multiple queries
async def process_queries_batch(queries: List[str], conversation_history=None) -> List[Tuple[str, List]]:
    """
    Process multiple queries concurrently for improved performance
    """
    tasks = [answer_query_async(query, conversation_history) for query in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle any exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            app_logger.error(f"Error processing query {i}: {str(result)}")
            processed_results.append((f"Error processing query: {str(result)}", []))
        else:
            processed_results.append(result)
    
    return processed_results


