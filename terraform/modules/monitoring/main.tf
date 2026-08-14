resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
  }
}

resource "kubernetes_namespace" "abst_gp" {
  metadata {
    name = "abst-gp-${var.environment}"
  }
}

# Prerequisites for Helm deployments will be managed here, e.g. service accounts.
# Note: Prometheus and Grafana will be deployed later via Helm / ArgoCD.
