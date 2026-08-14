import time
import sys

# Mock configuration
TARGET_GATEWAY = "http://localhost:8000/v7/gateway"
BATCH_SIZE = 100

class BackfillController:
    def __init__(self):
        self.paused = False
        self.progress = 0
        
    def pause(self):
        print("[BACKFILL] Pausing...")
        self.paused = True
        
    def resume(self):
        print("[BACKFILL] Resuming...")
        self.paused = False
        
    def start_backfill(self):
        print("[BACKFILL] BACKFILL_STARTED")
        # In a real scenario, this queries V5.5 DB directly for old documents
        mock_docs = [{"id": i, "content": f"Legacy doc {i}"} for i in range(500)]
        
        for doc in mock_docs:
            while self.paused:
                time.sleep(1)
                
            # Simulate CPU Limits / Windowing by adding sleep
            time.sleep(0.05)
            
            # Send to Gateway Sanitize -> Vector Router
            # requests.post(f"{TARGET_GATEWAY}/sanitize", json={"content": doc["content"], ...})
            
            self.progress += 1
            if self.progress % BATCH_SIZE == 0:
                print(f"[BACKFILL] Progress: {self.progress}/{len(mock_docs)}")
                
        print("[BACKFILL] BACKFILL_COMPLETED")

if __name__ == "__main__":
    controller = BackfillController()
    controller.start_backfill()
