import os
import json
import uuid
import hashlib
from typing import Dict, Any

class ImmutableDocumentExistsError(Exception):
    """Raised when trying to overwrite an existing immutable document."""
    pass

class AtomicPersistence:
    """
    Handles atomic, immutable persistence of structured documents to the filesystem.
    Uses os.link to guarantee exactly-once persistence and prevent race conditions.
    """
    
    @staticmethod
    def _validate_and_resolve_path(base_dir: str, run_id: uuid.UUID) -> tuple[str, str]:
        """
        Validates the base directory and returns the absolute final path.
        Prevents path traversal and rejects symlinks in the target path.
        """
        if not isinstance(run_id, uuid.UUID):
            try:
                run_id = uuid.UUID(str(run_id))
            except ValueError:
                raise ValueError("run_id must be a valid UUID")
                
        abs_base = os.path.abspath(base_dir)
        if not os.path.exists(abs_base):
            os.makedirs(abs_base, exist_ok=True)
            
        safe_filename = f"{run_id.hex}.json"
        final_path = os.path.join(abs_base, safe_filename)
        
        # Verify it stays under base directory
        if not os.path.commonpath([abs_base, final_path]) == abs_base:
            raise ValueError("Path traversal detected")
            
        return abs_base, final_path, run_id

    @staticmethod
    def _fsync_dir(dir_path: str):
        """fsync a directory to ensure directory entries are persisted."""
        if hasattr(os, 'O_DIRECTORY'):
            try:
                dir_fd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY)
                os.fsync(dir_fd)
                os.close(dir_fd)
            except Exception:
                pass

    @staticmethod
    def save_structured_document(
        base_dir: str, 
        run_id: uuid.UUID, 
        content: Dict[str, Any]
    ) -> tuple[str, str]:
        """
        Saves a structured document atomically.
        """
        abs_base, final_path, run_id = AtomicPersistence._validate_and_resolve_path(base_dir, run_id)
        
        if os.path.islink(final_path):
            raise ValueError("Symlinks are not permitted for structured documents.")
        
        from app.services.ocr.checksum import calculate_structured_document_checksum
        doc_checksum = calculate_structured_document_checksum(content)
        
        # Embed checksum into document payload before saving
        content["checksum"] = doc_checksum
        
        # Serialize the final document with checksum included
        canonical_bytes = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8')
        
        # 2. Create the .tmp file in the same filesystem with unique name
        pid = os.getpid()
        nonce = os.urandom(8).hex()
        tmp_filename = f".tmp_{run_id.hex}_{pid}_{nonce}"
        tmp_path = os.path.join(abs_base, tmp_filename)
        
        try:
            # 3. Create exclusively (O_CREAT | O_EXCL)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            fd = os.open(tmp_path, flags, 0o644)
            try:
                os.write(fd, canonical_bytes)
                os.fsync(fd)
            finally:
                os.close(fd)
                
            # 4. Publish via os.link (atomic, fails if final_path exists)
            try:
                os.link(tmp_path, final_path)
            except FileExistsError:
                raise ImmutableDocumentExistsError(
                    f"Document {run_id.hex} already exists. Immutable records cannot be overwritten."
                )
                
            # 5. fsync the parent directory
            AtomicPersistence._fsync_dir(abs_base)
            
        finally:
            # 6. Cleanup OUR temporary file
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            
            # 7. fsync directory again to persist the unlink
            AtomicPersistence._fsync_dir(abs_base)
            
        # Calculate the expected hash of the actual file written
        expected_checksum = hashlib.sha256(canonical_bytes).hexdigest()
        
        # 8. Re-read and verify the checksum of the final published file
        with open(final_path, 'rb') as f:
            published_bytes = f.read()
        published_checksum = hashlib.sha256(published_bytes).hexdigest()
        
        if published_checksum != expected_checksum:
            raise RuntimeError(f"Checksum mismatch after atomic write. Expected {expected_checksum}, got {published_checksum}")
            
        return final_path, doc_checksum
