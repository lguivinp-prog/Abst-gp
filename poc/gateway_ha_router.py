import random
import time

class GatewayNode:
    def __init__(self, node_id, health_rate=0.9):
        self.node_id = node_id
        self.health_rate = health_rate # Probability of processing correctly vs crashing
        self.is_down = False
        
    def process_request(self, data):
        if self.is_down:
            raise ConnectionError(f"Node {self.node_id} is dead.")
            
        # Simulate processing time
        time.sleep(0.01)
        
        if random.random() > self.health_rate:
            raise TimeoutError(f"Node {self.node_id} degraded / timed out.")
            
        return f"[MASKED_BY_{self.node_id}] {data}"

class GatewayRouter:
    def __init__(self, nodes):
        self.nodes = nodes
        self.max_retries = 2
        
    def get_healthy_node(self):
        healthy = [n for n in self.nodes if not n.is_down]
        if not healthy:
            return None
        return random.choice(healthy)
        
    def route_request(self, data):
        retries = 0
        while retries <= self.max_retries:
            node = self.get_healthy_node()
            
            if not node:
                print("ROUTER ALERT: All nodes are down. FAIL CLOSED.")
                return "FAIL_CLOSED"
                
            try:
                # Attempt to process
                result = node.process_request(data)
                return result
            except (ConnectionError, TimeoutError) as e:
                print(f"ROUTER: {e} -> Retrying...")
                retries += 1
                
        print("ROUTER ALERT: Max retries exceeded. FAIL CLOSED.")
        return "FAIL_CLOSED"

if __name__ == "__main__":
    print("--- GATEWAY HA SCENARIOS ---")
    
    # 1. Escenario Normal
    print("\nScenario 1: Healthy Cluster")
    nodes = [GatewayNode("A", 1.0), GatewayNode("B", 1.0)]
    router = GatewayRouter(nodes)
    print("Result:", router.route_request("SECRET_DATA"))
    
    # 2. Escenario Degradado (Nodo A falla temporalmente)
    print("\nScenario 2: Degraded Node (Timeout)")
    nodes = [GatewayNode("A", 0.0), GatewayNode("B", 1.0)]
    router = GatewayRouter(nodes)
    print("Result:", router.route_request("SECRET_DATA"))
    
    # 3. Escenario Caida Total (Nodos Muertos)
    print("\nScenario 3: Total Outage")
    nodes = [GatewayNode("A", 1.0), GatewayNode("B", 1.0)]
    nodes[0].is_down = True
    nodes[1].is_down = True
    router = GatewayRouter(nodes)
    print("Result:", router.route_request("SECRET_DATA"))
