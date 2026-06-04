#!/usr/bin/env python3

#This script runs the channel sounder in the testbed and exports the data to the storage server

import sys, os
import paramiko, subprocess
from datetime import datetime
import time
import traceback
import logging
import json
import argparse
from kafka import KafkaProducer

#**************************************************************
# Params
#-------

#**************************************************************
logsdir = '/tmp/'	       # Log directory
loglvl = logging.INFO	  # Log level
logging.getLogger('kafka').setLevel(logging.INFO) # Kafka logging level
logging.getLogger('paramiko').setLevel(logging.INFO) # Paramiko SSH client logging level

# The nodes to run the experiment in
# Load node inventory from a JSON file (`nodes.json`) to make the script reusable.
# The path can be overridden by setting the environment variable `CS_NODES_FILE`.
script_dir = os.path.dirname(__file__)
default_nodes_file = os.path.join(script_dir, 'nodes.json')
nodes_file = os.environ.get('CS_NODES_FILE', default_nodes_file)

try:
	with open(nodes_file, 'r') as nf:
		nodes = json.load(nf)
except Exception as e:
	logging.error(f"Failed to load node inventory from {nodes_file}: {e}")
	logging.error("Provide a valid JSON inventory file and set CS_NODES_FILE if it is in a different location.")
	sys.exit(1)

# The name of the experiment container that will run the spectrum monitoring
#ctnr = "M-VM-0002"

# The experiment duration for each node
dur = 20	# in seconds (s)

# The path to the volume containing the experiment results on each node
localResults = os.environ.get("CS_LOCAL_RESULTS", "/home/aerpawops/channel_sounder")

temp_log_dir = os.environ.get("CS_TEMP_LOG_DIR", "/home/aerpawops/temp_channel_sounder")
# The destination directory for all the results, and max storage allowable
#resultsStore = "/var/nfs/aerpaw/channel_sounder"   # This is an NFS share on the storage server
#storageLimit = 200      # in MegaBytes (MB)

# The user that will connect to the nodes and run the channel sounder experiments
# Use the same environment-driven defaults as channelSounder.py so these values may be
# provided at runtime by other tools or CI secret stores.
user = os.environ.get("CS_SSH_USER", "")
identity = os.environ.get("CS_SSH_KEY", "")
# Optional sudo password for remote commands (empty means assume passwordless sudo)
sudo_password = os.environ.get("CS_SUDO_PASSWORD", "")
#**************************************************************
# Funcs
#------

# Connect to a node
def connectTo(name: str, ip: str):
	if ip:
		client = paramiko.SSHClient()
		client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		key = paramiko.RSAKey.from_private_key_file(identity)
		try:
			logging.info(f"Connecting to {name} at {ip}:22")
			client.connect(ip, port=22, username=user, pkey=key)
		except Exception as e:
			logging.error(f"Unable to connect to host {name}")
			traceback.print_tb(e.__traceback__)
			client.close()
			return None
		return client
	else:
		logging.error(f"No target IP specified for connection")
		return None;

# Run a command on a connected node
def sshCmd(client: paramiko.SSHClient, cmd: str) -> (str, str, int):
	if client and client.get_transport():      #Check if client is open
		pwdneeded = True if cmd.startswith("sudo") else False
		stdin, stdout, stderr = client.exec_command(cmd)
		if pwdneeded:
			# If a sudo password is provided via env, use it; otherwise assume passwordless sudo.
			if sudo_password:
				stdin.write(f"{sudo_password}\n")
				stdin.flush()
		output = stdout.read().decode().rstrip()
#		print(output)
		err = stderr.read().decode().rstrip()
#		print(err)
		fail = stdout.channel.recv_exit_status()
		return output, err, fail
	else:
		logging.error("Client not connected")
		return

# Get state of container on node
def getVMState(client: paramiko.SSHClient, vm: str) -> str:
	if client and client.get_transport():      #Check if client is open
		cmd = f"sudo -S docker container inspect --format='{{{{.State.Status}}}}' {vm}"
		logging.debug(f"Executing: {cmd}")
		output, err, fail = sshCmd(client, cmd)
		logging.debug(f"Exit code: {fail}")
		if fail:
			logging.error(f"Container {vm} does not exist on remote host")
			client.close()
			return
		else:
			return output
	else:
		logging.error("Client not connected")
		return

#**************************************************************
# Main
#-----
if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO,
		format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
		handlers=[
			logging.StreamHandler()
		])

	# Set up command line parser
	parser = argparse.ArgumentParser(
		prog="Channel Sounder",
		description="Runs a channel sounder experiment to test reception between fixed nodes")
	parser.add_argument('-c', '--config', required=True, help="The config file for specifying the chains to test")
	
	args = parser.parse_args()
		
	#1. Unpause containers
	workingnodes = []
	for nodename, [nodeip, ctnr] in nodes.items():
		client = connectTo(nodename, nodeip)
		state = getVMState(client, ctnr)
		if state in ['paused', 'created', 'running', 'exited']:
			logging.info(f"{nodename}: Container {ctnr} state {state} -- node in valid state")
			workingnodes.append([nodename, nodeip])
		else:   #This definitely needs someone to look at what is happening
			logging.error(f"{nodename}: Container {ctnr} state {state} -- Skipping node")
			continue
		client.close()


	# Read in test json and build tests
	with open(args.config, 'r') as file:
		data = json.load(file)

	for group in data["test_groups"]:
		group_name = group["group_name"]
		group_test_dur = group["test_duration"]
		transmitters = []
		receivers = []
		for chain in group["chains"]:
			if chain["node_name"] not in [node[0] for node in workingnodes ]:
				logging.error(f"{chain['node_name']} not in list of working nodes: {workingnodes}")
				continue
			if chain["transmission_type"] == "TX":
				transmitters.append(chain)
			elif chain["transmission_type"] == "RX":
				receivers.append(chain)

		# Create list of receiver tests
		receiver_tests = []
		while len(receivers) != 0:
			test = []
			for i in range(len(receivers) - 1, -1, -1):
				# Iterate through test to make sure no duplicate nodes
				isFound = False
				for t in test:
					if t["serial_number"] == receivers[i]["serial_number"]:
						isFound = True
				# If not found, add to test and delete from receivers
				if not isFound:
					test.append(receivers[i])
					del receivers[i]
					
			receiver_tests.append(test)
		receiver_tests.reverse()

		print("Transmitters: ", json.dumps(transmitters, indent=4))
		print("Receivers: ", json.dumps(receiver_tests, indent=4))
