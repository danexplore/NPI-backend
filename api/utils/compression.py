"""
Sistema de Compressão de Resposta para NPI-backend
Implementa compressão inteligente de respostas HTTP para melhorar performance.
"""

import gzip
import brotli
import json
from typing import Dict, Any, Optional, Union, List
from io import BytesIO

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import compression_config
from ..utils.logging import performance_logger

# ========== TIPOS DE COMPRESSÃO ==========

class CompressionType:
    """Tipos de compressão suportados."""
    
    GZIP = "gzip"
    BROTLI = "br"
    DEFLATE = "deflate"
    
    @classmethod
    def get_supported(cls) -> List[str]:
        """Retorna lista de tipos suportados."""
        return [cls.GZIP, cls.BROTLI, cls.DEFLATE]

# ========== COMPRESSOR ==========

class ResponseCompressor:
    """Classe para compressão de respostas."""
    
    def __init__(self):
        self.stats = {
            "total_responses": 0,
            "compressed_responses": 0,
            "bytes_saved": 0,
            "compression_time": 0.0
        }
    
    def should_compress(
        self, 
        content: bytes, 
        content_type: str,
        size_threshold: int = None
    ) -> bool:
        """Verifica se deve comprimir baseado em tamanho e tipo de conteúdo."""
        
        if size_threshold is None:
            size_threshold = compression_config.MIN_SIZE_TO_COMPRESS
        
        # Verifica tamanho mínimo
        if len(content) < size_threshold:
            return False
        
        # Verifica tipo de conteúdo
        compressible_types = [
            "application/json",
            "text/plain",
            "text/html",
            "text/css",
            "text/javascript",
            "application/javascript",
            "application/xml",
            "text/xml"
        ]
        
        return any(content_type.startswith(ct) for ct in compressible_types)
    
    def get_best_encoding(self, accept_encoding: str) -> Optional[str]:
        """Determina melhor método de compressão baseado no Accept-Encoding."""
        
        if not accept_encoding:
            return None
        
        # Normaliza header
        encodings = [enc.strip().lower() for enc in accept_encoding.split(",")]
        
        # Prioridade: brotli > gzip > deflate
        if compression_config.ENABLE_BROTLI and CompressionType.BROTLI in encodings:
            return CompressionType.BROTLI
        elif compression_config.ENABLE_GZIP and CompressionType.GZIP in encodings:
            return CompressionType.GZIP
        elif compression_config.ENABLE_DEFLATE and CompressionType.DEFLATE in encodings:
            return CompressionType.DEFLATE
        
        return None
    
    def compress_content(self, content: bytes, encoding: str) -> bytes:
        """Comprime conteúdo usando o método especificado."""
        
        if encoding == CompressionType.GZIP:
            return self._compress_gzip(content)
        elif encoding == CompressionType.BROTLI:
            return self._compress_brotli(content)
        elif encoding == CompressionType.DEFLATE:
            return self._compress_deflate(content)
        else:
            raise ValueError(f"Unsupported compression type: {encoding}")
    
    def _compress_gzip(self, content: bytes) -> bytes:
        """Comprime usando GZIP."""
        buffer = BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode='wb', compresslevel=compression_config.GZIP_LEVEL) as f:
            f.write(content)
        return buffer.getvalue()
    
    def _compress_brotli(self, content: bytes) -> bytes:
        """Comprime usando Brotli."""
        return brotli.compress(content, quality=compression_config.BROTLI_QUALITY)
    
    def _compress_deflate(self, content: bytes) -> bytes:
        """Comprime usando Deflate."""
        import zlib
        return zlib.compress(content, compression_config.DEFLATE_LEVEL)
    
    def compress_json(self, data: Dict[str, Any], encoding: str) -> bytes:
        """Comprime dados JSON diretamente."""
        
        # Serializa JSON de forma otimizada
        if compression_config.USE_ORJSON:
            try:
                import orjson
                json_bytes = orjson.dumps(data)
            except ImportError:
                json_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8')
        else:
            json_bytes = json.dumps(data, separators=(',', ':')).encode('utf-8')
        
        return self.compress_content(json_bytes, encoding)
    
    def update_stats(self, original_size: int, compressed_size: int, compression_time: float):
        """Atualiza estatísticas de compressão."""
        self.stats["total_responses"] += 1
        self.stats["compressed_responses"] += 1
        self.stats["bytes_saved"] += original_size - compressed_size
        self.stats["compression_time"] += compression_time
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas de compressão."""
        stats = self.stats.copy()
        
        if stats["total_responses"] > 0:
            stats["compression_ratio"] = stats["compressed_responses"] / stats["total_responses"]
        else:
            stats["compression_ratio"] = 0.0
        
        if stats["compressed_responses"] > 0:
            stats["avg_compression_time"] = stats["compression_time"] / stats["compressed_responses"]
            stats["avg_bytes_saved"] = stats["bytes_saved"] / stats["compressed_responses"]
        else:
            stats["avg_compression_time"] = 0.0
            stats["avg_bytes_saved"] = 0.0
        
        return stats

# ========== MIDDLEWARE ==========

class CompressionMiddleware(BaseHTTPMiddleware):
    """Middleware para compressão automática de respostas."""
    
    def __init__(self, app):
        super().__init__(app)
        self.compressor = ResponseCompressor()
    
    async def dispatch(self, request: Request, call_next):
        """Processa request e comprime resposta se apropriado."""
        
        # Executa request
        response = await call_next(request)
        
        # Verifica se deve comprimir
        if not self._should_process_response(request, response):
            return response
        
        # Obtém método de compressão
        accept_encoding = request.headers.get("accept-encoding", "")
        encoding = self.compressor.get_best_encoding(accept_encoding)
        
        if not encoding:
            return response
        
        # Lê conteúdo da resposta
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
        
        # Verifica se deve comprimir baseado no conteúdo
        content_type = response.headers.get("content-type", "")
        if not self.compressor.should_compress(response_body, content_type):
            # Retorna resposta original se não deve comprimir
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.media_type
            )
        
        # Comprime conteúdo
        import time
        start_time = time.time()
        
        try:
            compressed_content = self.compressor.compress_content(response_body, encoding)
            compression_time = time.time() - start_time
            
            # Atualiza estatísticas
            self.compressor.update_stats(
                len(response_body),
                len(compressed_content),
                compression_time
            )
            
            # Log da compressão
            performance_logger.info(
                "Response compressed",
                encoding=encoding,
                original_size=len(response_body),
                compressed_size=len(compressed_content),
                compression_ratio=round(len(compressed_content) / len(response_body), 2),
                compression_time=round(compression_time * 1000, 2),
                path=str(request.url)
            )
            
            # Cria nova resposta comprimida
            headers = dict(response.headers)
            headers["Content-Encoding"] = encoding
            headers["Content-Length"] = str(len(compressed_content))
            headers["Vary"] = "Accept-Encoding"
            
            return Response(
                content=compressed_content,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type
            )
            
        except Exception as e:
            performance_logger.error(
                "Compression failed",
                error=str(e),
                encoding=encoding,
                path=str(request.url)
            )
            
            # Retorna resposta original em caso de erro
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.media_type
            )
    
    def _should_process_response(self, request: Request, response: Response) -> bool:
        """Verifica se deve processar a resposta."""
        
        # Não comprime se já está comprimido
        if "content-encoding" in response.headers:
            return False
        
        # Não comprime erros de servidor
        if response.status_code >= 500:
            return False
        
        # Não comprime endpoints de streaming
        if "stream" in str(request.url).lower():
            return False
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtém estatísticas do middleware."""
        return self.compressor.get_stats()

# ========== RESPONSE HELPERS ==========

class CompressedJSONResponse(JSONResponse):
    """JSONResponse com compressão automática."""
    
    def __init__(
        self, 
        content: Any, 
        status_code: int = 200, 
        headers: Optional[Dict[str, str]] = None,
        force_compression: bool = False,
        compression_type: Optional[str] = None
    ):
        self.force_compression = force_compression
        self.compression_type = compression_type
        super().__init__(content, status_code, headers)
    
    def render(self, content: Any) -> bytes:
        """Renderiza conteúdo com compressão opcional."""
        
        # Serializa JSON
        if compression_config.USE_ORJSON:
            try:
                import orjson
                json_bytes = orjson.dumps(content)
            except ImportError:
                json_bytes = json.dumps(content, separators=(',', ':')).encode('utf-8')
        else:
            json_bytes = json.dumps(content, separators=(',', ':')).encode('utf-8')
        
        # Comprime se forçado
        if self.force_compression and self.compression_type:
            compressor = ResponseCompressor()
            
            try:
                compressed_bytes = compressor.compress_content(json_bytes, self.compression_type)
                
                # Adiciona headers de compressão
                self.headers["Content-Encoding"] = self.compression_type
                self.headers["Content-Length"] = str(len(compressed_bytes))
                self.headers["Vary"] = "Accept-Encoding"
                
                return compressed_bytes
                
            except Exception:
                # Retorna original se compressão falhar
                pass
        
        return json_bytes

# ========== UTILITÁRIOS ==========

def compress_large_response(data: Dict[str, Any], min_size: int = 1024) -> Union[Dict[str, Any], bytes]:
    """Comprime resposta grande automaticamente."""
    
    # Serializa para verificar tamanho
    json_str = json.dumps(data, separators=(',', ':'))
    
    if len(json_str) < min_size:
        return data
    
    # Comprime usando gzip
    compressor = ResponseCompressor()
    compressed = compressor.compress_content(json_str.encode('utf-8'), CompressionType.GZIP)
    
    return compressed

def estimate_compression_savings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Estima economia de compressão para dados."""
    
    json_str = json.dumps(data, separators=(',', ':'))
    original_size = len(json_str.encode('utf-8'))
    
    compressor = ResponseCompressor()
    
    savings = {
        "original_size": original_size,
        "estimated_savings": {}
    }
    
    for compression_type in CompressionType.get_supported():
        try:
            compressed = compressor.compress_content(json_str.encode('utf-8'), compression_type)
            compressed_size = len(compressed)
            ratio = compressed_size / original_size
            
            savings["estimated_savings"][compression_type] = {
                "compressed_size": compressed_size,
                "compression_ratio": round(ratio, 2),
                "bytes_saved": original_size - compressed_size,
                "percentage_saved": round((1 - ratio) * 100, 1)
            }
        except Exception:
            savings["estimated_savings"][compression_type] = {
                "error": "Compression failed"
            }
    
    return savings

# ========== INSTÂNCIA GLOBAL ==========

_global_compressor = None

def get_compressor() -> ResponseCompressor:
    """Obtém instância global do compressor."""
    global _global_compressor
    if _global_compressor is None:
        _global_compressor = ResponseCompressor()
    return _global_compressor
