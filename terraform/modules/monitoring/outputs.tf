output "monitoring_namespace" {
  value = kubernetes_namespace.monitoring.metadata[0].name
}

output "app_namespace" {
  value = kubernetes_namespace.abst_gp.metadata[0].name
}
