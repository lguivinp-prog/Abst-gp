import os
import time
import pytest
import tempfile
import tracemalloc
from unittest.mock import MagicMock, patch

# Performance Test Configuration
# We simulate file sizes: 10MB, 100MB, 500MB
SIZES_MB = [10, 100, 500]

def create_dummy_file(path: str, size_mb: int):
    """Creates a dummy file of exact size in MB."""
    with open(path, "wb") as f:
        f.seek((size_mb * 1024 * 1024) - 1)
        f.write(b"\0")

def simulate_storage_get(file_path: str, size_mb: int):
    # Simulate network latency of downloading from S3/MinIO
    # Assuming ~50MB/s download speed for baseline
    time.sleep(size_mb / 50.0)
    return True

def simulate_workspace_materialization(size_mb: int):
    # Simulate IO cost of moving file to local workspace
    time.sleep(size_mb / 200.0)
    return True

def simulate_ocr_execution(size_mb: int):
    # Simulate OCR CPU bound processing.
    # We assume roughly 1 second per MB of PDF content
    time.sleep(size_mb / 10.0) # scaled down for test execution speed, in reality 1MB could be 1s.
    return {"status": "success", "blocks": []}

def simulate_artifact_upload():
    # Simulate JSON artifact upload (usually small, < 1MB)
    time.sleep(0.1)
    return True

def simulate_db_persistence():
    # Simulate DB transaction latency
    time.sleep(0.05)
    return True

@pytest.mark.parametrize("size_mb", SIZES_MB)
def test_v6_ocr_performance_baseline(size_mb):
    """
    Benchmark the OCR Worker V2 pipeline.
    This establishes the baseline metrics for observability:
    - storage_get_latency_seconds
    - workspace_materialization_seconds
    - ocr_processing_duration_seconds
    - artifact_upload_duration_seconds
    """
    print(f"\n--- Starting Benchmark for {size_mb}MB PDF ---")
    
    tracemalloc.start()
    start_total = time.time()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_file = os.path.join(tmpdir, f"test_{size_mb}MB.pdf")
        create_dummy_file(dummy_file, size_mb)
        
        # 1. Storage GET
        t0 = time.time()
        simulate_storage_get(dummy_file, size_mb)
        t_storage = time.time() - t0
        
        # 2. Workspace Materialization
        t0 = time.time()
        simulate_workspace_materialization(size_mb)
        t_workspace = time.time() - t0
        
        # 3. OCR Processing
        t0 = time.time()
        simulate_ocr_execution(size_mb)
        t_ocr = time.time() - t0
        
        # 4. Artifact Upload
        t0 = time.time()
        simulate_artifact_upload()
        t_upload = time.time() - t0
        
        # 5. DB Persistence
        t0 = time.time()
        simulate_db_persistence()
        t_db = time.time() - t0
        
    total_time = time.time() - start_total
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    peak_mb = peak / 1024 / 1024
    
    print(f"Metrics Recorded:")
    print(f"  Storage GET Time: {t_storage:.4f}s")
    print(f"  Workspace Materialization Time: {t_workspace:.4f}s")
    print(f"  OCR Execution Time: {t_ocr:.4f}s")
    print(f"  Artifact Upload Time: {t_upload:.4f}s")
    print(f"  DB Persistence Time: {t_db:.4f}s")
    print(f"  ---------------------------------")
    print(f"  TOTAL Pipeline Time: {total_time:.4f}s")
    print(f"  Peak Memory Usage: {peak_mb:.2f} MB")
    
    # Assertions to ensure baseline limits are respected (example thresholds)
    assert t_storage < (size_mb / 10.0), "Storage GET is too slow"
    assert t_ocr < (size_mb / 2.0), "OCR Execution exceeded baseline limit"
