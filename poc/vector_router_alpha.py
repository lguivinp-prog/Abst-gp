class VectorEngineRouter:
    def __init__(self, mode="FAISS_ONLY"):
        # Modes: FAISS_ONLY, DUAL_WRITE, DUAL_READ, PGVECTOR_PRIMARY
        self.mode = mode
        self.faiss_mock = []
        self.pgvector_mock = []

    def write(self, chunk):
        if self.mode == "FAISS_ONLY":
            self.faiss_mock.append(chunk)
            print(f"[WRITE] FAISS Only: {chunk}")
        elif self.mode in ("DUAL_WRITE", "DUAL_READ"):
            self.faiss_mock.append(chunk)
            self.pgvector_mock.append(chunk)
            print(f"[WRITE] Dual Write (FAISS + pgvector): {chunk}")
        elif self.mode == "PGVECTOR_PRIMARY":
            self.pgvector_mock.append(chunk)
            print(f"[WRITE] PGVECTOR Primary: {chunk}")

    def read(self, query):
        if self.mode == "FAISS_ONLY":
            print(f"[READ] From FAISS: {query}")
            return "Faiss_Result"
        elif self.mode == "DUAL_WRITE":
            # Write to both, but read from legacy Faiss
            print(f"[READ] From FAISS (Shadowing pgvector): {query}")
            return "Faiss_Result"
        elif self.mode == "DUAL_READ":
            # Read from both to compare recall/latency
            print(f"[READ] Comparing FAISS vs PGVECTOR: {query}")
            return "Dual_Read_Match"
        elif self.mode == "PGVECTOR_PRIMARY":
            print(f"[READ] From PGVECTOR: {query}")
            return "Pgvector_Result"

if __name__ == "__main__":
    print("--- VECTOR ROUTER STRATEGY POC ---")
    router = VectorEngineRouter("FAISS_ONLY")
    router.write("Doc1")
    router.read("Q1")
    
    print("\n--- TRANSITION TO DUAL WRITE ---")
    router.mode = "DUAL_WRITE"
    router.write("Doc2")
    router.read("Q2")

    print("\n--- TRANSITION TO DUAL READ (VALIDATION) ---")
    router.mode = "DUAL_READ"
    router.read("Q3")
    
    print("\n--- TRANSITION TO PGVECTOR PRIMARY ---")
    router.mode = "PGVECTOR_PRIMARY"
    router.write("Doc3")
    router.read("Q4")
    
    print("\n--- ROLLBACK SCENARIO ---")
    router.mode = "FAISS_ONLY"
    router.write("Doc4")
    router.read("Q5")
