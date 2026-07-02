
# OPENZERO AUTO-GENERATED CONTAINER
FROM ubuntu:22.04

# ENV SETUP
ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# DEPENDENCIES
RUN apt-get update && apt-get install -y     python3 python3-pip nodejs npm curl wget git     ca-certificates fonts-liberation libasound2     && rm -rf /var/lib/apt/lists/*

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
