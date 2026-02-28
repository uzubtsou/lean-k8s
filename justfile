default:
    @just --list

# Create a k3d cluster
k3d-up:
    k3d cluster create --config runtimes/k3d/config.yaml

# Delete the k3d cluster
k3d-down:
    k3d cluster delete lean-k8s

# Stop the k3d cluster
k3d-stop:
    k3d cluster stop lean-k8s

# Start a stopped k3d cluster
k3d-start:
    k3d cluster start lean-k8s
