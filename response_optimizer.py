import gzip
import brotli
import zstandard as zstd
import json
from typing import Any, Dict, Union
import time
from src.logging_config import app_logger

class ResponseOptimizer:
    """Optimizes responses through compression and streaming"""
    
    def __init__(self):
        self.compression_stats = {
            "total_responses": 0,
            "compression_enabled": 0,
            "bytes_saved": 0,
            "avg_compression_ratio": 0.0
        }
    
    def compress_response(self, data: Union[str, Dict], method: str = "brotli") -> bytes:
        """
        Compress response data using specified method
        
        :param data: Data to compress (string or dict)
        :param method: Compression method ('gzip', 'brotli', 'zstd')
        :return: Compressed bytes
        """
        start_time = time.time()
        
        try:
            # Convert to string if dict
            if isinstance(data, dict):
                data_str = json.dumps(data, separators=(',', ':'))
            else:
                data_str = str(data)
            
            original_size = len(data_str.encode('utf-8'))
            
            # Choose compression method
            if method == "gzip":
                compressed = gzip.compress(data_str.encode('utf-8'), compresslevel=6)
            elif method == "brotli":
                compressed = brotli.compress(data_str.encode('utf-8'), quality=6)
            elif method == "zstd":
                cctx = zstd.ZstdCompressor(level=6)
                compressed = cctx.compress(data_str.encode('utf-8'))
            else:
                # Fallback to no compression
                compressed = data_str.encode('utf-8')
            
            compressed_size = len(compressed)
            compression_ratio = (original_size - compressed_size) / original_size
            
            # Update stats
            self.compression_stats["total_responses"] += 1
            if compression_ratio > 0:
                self.compression_stats["compression_enabled"] += 1
                self.compression_stats["bytes_saved"] += (original_size - compressed_size)
                
                # Update average compression ratio
                self.compression_stats["avg_compression_ratio"] = (
                    self.compression_stats["bytes_saved"] / 
                    (self.compression_stats["total_responses"] * original_size)
                )
            
            processing_time = time.time() - start_time
            app_logger.debug(f"Compression ({method}): {original_size} -> {compressed_size} bytes "
                           f"({compression_ratio:.1%} reduction) in {processing_time:.3f}s")
            
            return compressed
            
        except Exception as e:
            app_logger.error(f"Compression error with {method}: {str(e)}")
            # Return uncompressed data as fallback
            return data_str.encode('utf-8') if isinstance(data, str) else json.dumps(data).encode('utf-8')
    
    def stream_response_chunks(self, response: str, chunk_size: int = 50) -> list:
        """
        Break response into chunks for streaming display
        
        :param response: Full response text
        :param chunk_size: Size of each chunk in characters
        :return: List of response chunks
        """
        if not response:
            return []
        
        # Split response into word-boundary chunks for better display
        words = response.split()
        chunks = []
        current_chunk = ""
        
        for word in words:
            if len(current_chunk) + len(word) + 1 <= chunk_size:
                current_chunk += word + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = word + " "
        
        # Add the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def optimize_json_response(self, data: Dict[str, Any]) -> str:
        """
        Optimize JSON response by removing unnecessary whitespace and sorting keys
        
        :param data: Dictionary to optimize
        :return: Optimized JSON string
        """
        try:
            # Remove None values and empty strings to reduce size
            cleaned_data = self._clean_dict(data)
            
            # Use compact JSON format
            return json.dumps(
                cleaned_data, 
                separators=(',', ':'),  # No spaces after separators
                sort_keys=True,         # Consistent ordering for caching
                ensure_ascii=False      # Allow Unicode characters
            )
        except Exception as e:
            app_logger.error(f"JSON optimization error: {str(e)}")
            return json.dumps(data)
    
    def _clean_dict(self, obj: Any) -> Any:
        """
        Recursively clean dictionary by removing None values and empty strings
        """
        if isinstance(obj, dict):
            return {
                k: self._clean_dict(v) 
                for k, v in obj.items() 
                if v is not None and v != "" and v != []
            }
        elif isinstance(obj, list):
            return [self._clean_dict(item) for item in obj if item is not None and item != ""]
        else:
            return obj
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression statistics"""
        return {
            **self.compression_stats,
            "compression_rate": (
                self.compression_stats["compression_enabled"] / 
                max(self.compression_stats["total_responses"], 1) * 100
            )
        }
    
    def estimate_transfer_time(self, data_size: int, connection_speed_mbps: float = 10.0) -> float:
        """
        Estimate transfer time for given data size
        
        :param data_size: Size in bytes
        :param connection_speed_mbps: Connection speed in Mbps
        :return: Estimated transfer time in seconds
        """
        # Convert Mbps to bytes per second
        bytes_per_second = connection_speed_mbps * 1024 * 1024 / 8
        return data_size / bytes_per_second
    
    def should_compress(self, data: Union[str, Dict], min_size: int = 1000) -> bool:
        """
        Determine if data should be compressed based on size
        
        :param data: Data to check
        :param min_size: Minimum size in bytes to consider compression
        :return: True if should compress
        """
        if isinstance(data, dict):
            data_str = json.dumps(data)
        else:
            data_str = str(data)
        
        return len(data_str.encode('utf-8')) >= min_size

# Global response optimizer instance
response_optimizer = ResponseOptimizer()