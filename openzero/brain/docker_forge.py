import os
import subprocess

def create_docker_infrastructure():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dockerfile_path = os.path.join(base_dir, "Dockerfile")
    
    # 1. DEFINE THE BLUEPRINT
    dockerfile_content = """
# OPENZERO AUTO-GENERATED CONTAINER
FROM ubuntu:22.04

# ENV SETUP
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# DEPENDENCIES
RUN apt-get update && apt-get install -y \
    python3 python3-pip nodejs npm curl wget git \
    ca-certificates fonts-liberation libasound2 \
    && rm -rf /var/lib/apt/lists/*

# PYTHON BRAIN
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# NODE HAND
COPY moltbot/package.json ./moltbot/
RUN cd moltbot && npm install

# SOURCE CODE
COPY . .

# PORTS
EXPOSE 1024 3000

# STARTUP
CMD ["/bin/bash", "./start_openzero_ui.sh"]
"""
    
    # 2. WRITE THE FILE
    with open(dockerfile_path, "w") as f:
        f.write(dockerfile_content)
        
    return "Dockerfile generated at " + dockerfile_path

def build_container():
    try:
        # Check if docker exists
        subprocess.check_call("docker --version", shell=True)
        return subprocess.check_output("docker build -t openzero-sovereign .", shell=True).decode()
    except:
        return "Docker not installed. Use 'run sudo apt install docker.io' first."
