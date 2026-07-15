import os
import multiprocessing
import tempfile
from app.services.extraction_engine.utils.persistence import AtomicPersistence, ImmutableDocumentExistsError

def worker(base_dir, doc_id, content, worker_id, results_queue):
    try:
        checksum = AtomicPersistence.save_structured_document(base_dir, doc_id, content)
        results_queue.put({"worker_id": worker_id, "status": "success", "checksum": checksum})
    except ImmutableDocumentExistsError as e:
        results_queue.put({"worker_id": worker_id, "status": "exists_error"})
    except Exception as e:
        results_queue.put({"worker_id": worker_id, "status": f"error: {str(e)}"})

def test_race_conditions():
    doc_id = "12345678-1234-5678-1234-567812345678"
    content = {"test": "data", "workers": 10}
    
    manager = multiprocessing.Manager()
    results_queue = manager.Queue()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        processes = []
        for i in range(10):
            p = multiprocessing.Process(target=worker, args=(tmpdir, doc_id, content, i, results_queue))
            processes.append(p)
            
        # Start all practically simultaneously
        for p in processes:
            p.start()
            
        for p in processes:
            p.join()
            
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())
            
        successes = [r for r in results if r["status"] == "success"]
        exists_errors = [r for r in results if r["status"] == "exists_error"]
        other_errors = [r for r in results if r["status"].startswith("error")]
        
        print(f"Total workers: 10")
        print(f"Successes (saved document): {len(successes)}")
        print(f"FileExistsError (prevented overwrite): {len(exists_errors)}")
        print(f"Other errors: {len(other_errors)}")
        if len(other_errors) > 0:
            print(f"First error: {other_errors[0]['status']}")
        
        if len(successes) == 1 and len(exists_errors) == 9 and len(other_errors) == 0:
            print("SUCCESS: Race condition test passed! Exactly ONE process succeeded.")
        else:
            print("FAILED: Race condition test did not yield expected exactly-once result.")

if __name__ == "__main__":
    test_race_conditions()
