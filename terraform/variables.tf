variable "aws_region" {
  description = "AWS Region"
  default     = "eu-central-1"
}

variable "project_name" {
  description = "Project name (used as prefix for all resources)"
  default     = "predictops"
}

variable "instance_type" {
  description = "EC2 instance type (t3.large recommended due to Ollama RAM requirements)"
  default     = "t3.large"
}

variable "key_name" {
  description = "Name of the AWS key pair for SSH access"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "IP address allowed SSH access (your IP + /32)"
  default     = "0.0.0.0/0"
}
