output "server_ip" {
  description = "Öffentliche IP des PredictOps Servers"
  value       = aws_eip.predictops.public_ip
}

output "chat_url" {
  description = "URL zum Chat Interface"
  value       = "http://${aws_eip.predictops.public_ip}"
}

output "grafana_url" {
  description = "URL zum Grafana Dashboard"
  value       = "http://${aws_eip.predictops.public_ip}/grafana"
}

output "ssh_command" {
  description = "SSH Befehl zum Verbinden"
  value       = "ssh -i ~/.ssh/${var.key_name}.pem ubuntu@${aws_eip.predictops.public_ip}"
}

output "s3_bucket" {
  description = "S3 Bucket Name für Daten"
  value       = aws_s3_bucket.data.bucket
}
