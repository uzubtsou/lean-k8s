default:
    @just --list

# Check if any clusters are running
check:
    @k3d cluster list

# Create the sandpit cluster
up:
    k3d cluster create --config runtimes/k3d/config.yaml

# Delete the sandpit cluster
down:
    k3d cluster delete sandpit

# Stop the sandpit cluster
stop:
    k3d cluster stop sandpit

# Start the sandpit cluster
start:
    k3d cluster start sandpit
