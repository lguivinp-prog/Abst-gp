from abc import ABC, abstractmethod
from typing import BinaryIO, Dict, Any, Optional

class DocumentStorage(ABC):
    @abstractmethod
    def put(self, tenant_id: str, document_id: str, file_stream: BinaryIO, expected_checksum: Optional[str] = None) -> str:
        """
        Guarda un stream de archivo y devuelve su URI/Path.
        Puede validar el checksum SHA-256 opcionalmente en tiempo de escritura.
        """
        pass
    
    @abstractmethod
    def get(self, uri: str) -> BinaryIO:
        """
        Devuelve el stream de un archivo dada su URI.
        """
        pass
        
    @abstractmethod
    def delete(self, uri: str) -> bool:
        """
        Elimina físicamente el archivo. Devuelve True si fue exitoso, False de lo contrario.
        """
        pass
        
    @abstractmethod
    def exists(self, uri: str) -> bool:
        """
        Verifica la existencia del archivo.
        """
        pass
        
    @abstractmethod
    def checksum(self, uri: str) -> str:
        """
        Calcula o recupera el checksum SHA-256 del archivo almacenado.
        """
        pass

    @abstractmethod
    def metadata(self, uri: str) -> Dict[str, Any]:
        """
        Recupera los metadatos asociados al objeto (tamaño, tipo, fechas, etc.).
        """
        pass

    @abstractmethod
    def generate_presigned_url(self, uri: str, expiration: int = 3600) -> str:
        """
        Genera una presigned URL para subir archivos directamente al storage.
        """
        pass
