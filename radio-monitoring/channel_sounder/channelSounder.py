#!/usr/bin/env python3

#This script runs the channel sounder in the testbed and exports the data to the ELK server

import sys, os
import argparse
import paramiko, subprocess
from datetime import datetime
import time
import traceback
import logging
import json
import re
from datetime import datetime, timedelta
from kafka import KafkaProducer

#**************************************************************
# Params
#-------

#**************************************************************
logsdir = '/tmp/'		   # Log directory
loglvl = logging.INFO	  # Log level
logging.getLogger('kafka').setLevel(logging.WARNING) # Kafka logging level
logging.getLogger('paramiko').setLevel(logging.INFO) # Paramiko SSH client logging level

# The nodes to run the experiment in
# Nodes inventory is loaded from a JSON file to make it easy to reuse the
# orchestration without editing Python source. The path can be overridden by
# setting the environment variable `CS_NODES_FILE`.
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
localResults = "/home/aerpawops/channel_sounder"

temp_log_dir = "/home/aerpawops/temp_channel_sounder"
# The destination directory for all the results, and max storage allowable
#resultsStore = "/var/nfs/aerpaw/channel_sounder"   # This is an NFS share on the storage server
#storageLimit = 200      # in MegaBytes (MB)

KAFKA_SERVERS = os.environ.get("CS_KAFKA_SERVERS", "192.168.60.202:9092").split(",")
# The user that will connect to the nodes and run the channel sounder experiments
user = os.environ.get("CS_SSH_USER", "")
identity = os.environ.get("CS_SSH_KEY", os.path.expanduser("~/.ssh/id_rsa"))
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
			# Enable keep-alive to prevent connection timeout during long experiments
			client.get_transport().set_keepalive(30)  # Send keep-alive every 30 seconds
		except Exception as e:
			logging.error(f"Unable to connect to host {name}")
			traceback.print_tb(e.__traceback__)
			client.close()
			return None
		return client
	else:
		logging.error(f"No target IP specified for connection")
		return None

# Run a command on a connected node
def sshCmd(client: paramiko.SSHClient, cmd: str):
	if client and client.get_transport():      #Check if client is open
		pwdneeded = True if cmd.startswith("sudo") else False
		stdin, stdout, stderr = client.exec_command(cmd)
		if pwdneeded and sudo_password:
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

# Pause/Unpause container
def pauseVM(client: paramiko.SSHClient, vm: str, act: bool = True) -> bool:
	if client and client.get_transport():      #Check if client is open
		action = 'pause' if act else 'unpause'
		cmd = f"sudo -S docker container {action} {vm}"
		logging.debug(f"Executing: {cmd}")
		output, err, fail = sshCmd(client, cmd)
		logging.debug(f"Exit code: {fail}")
		if fail:
			logging.error(f"Failed to {action} container {vm} on remote host")
			client.close()
			return False
		else:
			return True
	else:
		logging.error("Client not connected")
		return False

# Start/Stop container
def startVM(client: paramiko.SSHClient, vm: str, act: bool = True) -> bool:
	if client and client.get_transport():      #Check if client is open
		action = 'start' if act else 'stop'
		cmd = f"sudo -S docker container {action} {vm}"
		logging.debug(f"Executing: {cmd}")
		output, err, fail = sshCmd(client, cmd)
		logging.debug(f"Exit code: {fail}")
		if fail:
			logging.error(f"Failed to {action} container {vm} on remote host")
			client.close()
			return False
		else:
			return True
	else:
		logging.error("Client not connected")
		return False

# Transfers the results to the destination directory
def transferFile(node: str, filename: str, src_path: str, dest_path: str) -> bool:
	cmd = f"scp -i {identity} {user}@{node}:{src_path}/{filename} {dest_path}/{filename}"
	cmd = cmd.split()
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	output, err = p.communicate()
	if output: logging.debug(f"{output.decode().rstrip()}")
	if err: logging.debug(f"{err.decode().rstrip()}")
	return False if p.returncode else True

# Returns folder size in MB
def get_folder_size(folderpath: str):
	tot_size = 0
	for dirpath, dirnames, filenames in os.walk(folderpath):
		for f in filenames:
			fp = os.path.join(dirpath, f)
			tot_size += os.path.getsize(fp)
	return tot_size / (1024 * 1024)

# Deletes oldest files in folder until total size below the specified threshold
def cleanup_folder(folderpath: str, max_mb: int):
	size = get_folder_size(folderpath)
	logging.debug(f"Folder size = {size}MB")

	while size > max_mb:
		files = []
		for dirpath, dirnames, filenames in os.walk(folderpath):
			for f in filenames:
				fp = os.path.join(dirpath, f)
				files.append((os.path.getmtime(fp), fp))
		files.sort()
		oldest_file = files[0][1]
		os.remove(oldest_file)
		logging.info(f"Deleted {oldest_file} to reduce folder size")
		size = get_folder_size(folderpath)

	size = round(size,2)
	logging.info(f"Folder size is below {max_mb}Mb at {size}Mb")

def calculate_average(log_content):
	values = []
	first_timestamp = None
	last_timestamp = None

	for line in log_content.splitlines():
		timestamp_match = re.search(r'\[(.*?)\]', line)
		value_match = re.search(r'\s+([-]?[0-9]*\.+[0-9]+)$', line.strip())

		if timestamp_match and value_match:
			if first_timestamp is None:
				first_timestamp = timestamp_match.group(1)
			last_timestamp = timestamp_match.group(1)

		if value_match:
			value = float(value_match.group(1))
			values.append(value)

	if values:
		values.pop(0)
		average = sum(values) / len(values)
		'''
		print(f'Average: {average:.5f}')
		print(f'First Timestamp: {first_timestamp}')
		print(f'Last Timestamp: {last_timestamp}')
		'''
		# Generate list of timestamps with 1-second increments
		start_time = datetime.strptime(first_timestamp, "%Y-%m-%d %H:%M:%S.%f")
		end_time = datetime.strptime(last_timestamp, "%Y-%m-%d %H:%M:%S.%f")
		timestamp_list = []

		current_time = start_time
		while current_time <= end_time:
			timestamp_list.append(current_time.strftime("%Y-%m-%d %H:%M:%S.%f"))
			current_time += timedelta(seconds=0.1)

		timestamp_list.append(end_time)
		return timestamp_list, average
	else:
		logging.warning("No numerical values found in log to calculate average.")
		return None, None

def send_log_to_kafka(producer, log_file_path, params):
	# Extract the file name from the path
	file_name = os.path.basename(log_file_path)
	file_name = file_name.split(":")

	log_type = file_name[-1][:-4]

	# Read the entire content of the file (if transmitter is not null)
	if params[0] == None:
		log_content = "Artificial log for transmitter annotation for control test"
	else:
		with open(log_file_path, "r") as file:
			log_content = file.read()
	# Special case if transmitter log
	if log_type == "radio_channelsoundertxgrc_log":
		message = {
			"transmitter": params[1],
			"transmitter_serial_number": params[2],
			"transmitter_channel": params[3],
			"transmitter_frequency": params[4],
			"log_type": log_type,
			"log_timestamp": file_name[-2],
			"log_content": log_content,
		}
	elif log_type == "radio_channelsounderrxgrc_log":
		message = {
			"transmitter": params[1],
			"transmitter_serial_number": params[2],
			"transmitter_channel": params[3],
			"transmitter_frequency": params[4],
			"receiver": params[5],
			"receiver_serial_number": params[6],
			"receiver_channel": params[7],
			"receiver_frequency": params[8],
			"log_type": log_type,
			"log_timestamp": file_name[-2],
			"log_content": log_content,
		}
	else:
		# For sending power and quality logs
		
		# Create a JSON object with filename and content
		message = {
			"transmitter": params[1],
			"transmitter_serial_number": params[2],
			"transmitter_channel": params[3],
			"transmitter_frequency": params[4],
			"receiver": params[5],
			"receiver_serial_number": params[6],
			"receiver_channel": params[7],
			"receiver_frequency": params[8],
			"log_type": log_type,
			"log_timestamp": file_name[5],
			"log_content": log_content
		}
		
		# Calculate average and send average_log to Kafka
		timestamp_list, average = calculate_average(log_content)
		average_log_content = ""
		if average is None:
			logging.error(f"Unable to calculate average for {params}")
		else:
			for timestamp in timestamp_list:
				average_log_content += f"[{timestamp}] 0000000 {average}\n"
			average_message = {
				"transmitter": params[1],
				"transmitter_serial_number": params[2],
				"transmitter_channel": params[3],
				"transmitter_frequency": params[4],
				"receiver": params[5],
				"receiver_serial_number": params[6],
				"receiver_channel": params[7],
				"receiver_frequency": params[8],
				"log_type": "average_" + log_type,
				"log_timestamp": file_name[5],
				"log_content": average_log_content
			}
			producer.send("channel_sounder_logging", value=average_message)

	# Send the message to Kafka
	producer.send("channel_sounder_logging", value=message)
	producer.flush()
	logging.debug(f"Sent completed log to Kafka: {file_name}")


def handler_upload_logs_to_kafka(client, node_name, params, producer):
	# USED IN CHANNEL SOUNDER EXPERIMENT
	# params:
	#   - log_prefix    only logs with this prefix should be uploaded
	#   - transmitter_node_name
	#   - transmitter_serial_number
	#   - transmitter_channel
	#   - trasmitter_frequency
	#   - receiver_node_name
	#   - receiver_serial_number
	#   - receiver_channel
	#   - receiver_frequency

	# Use the persistent client connection passed as parameter
	# Create temp log directory in node
	cmd = f"sudo -S mkdir -p {temp_log_dir}"
	logging.debug(f"Executing: {cmd}")
	output, err, fail = sshCmd(client, cmd)
	logging.debug(f"Exit code: {fail}")

	# Create temp log directory locally
	os.system(f"mkdir -p {temp_log_dir}")

	# Copy correct logs from E-VM to node
	cmd = f"sudo -S docker exec {nodes[node_name][1]} ls /root/Results"
	logging.debug(f"Executing: {cmd}")
	output, err, fail = sshCmd(client, cmd)
	logging.debug(f"Exit code: {fail}")
	if fail:
		logging.debug(f"Error: {err}")
	
	e_vm_log_files = []
	for log_file in output.splitlines():
		if params[0] in log_file:
			e_vm_log_files.append(log_file)

	for log_file in e_vm_log_files:
		cmd = f"sudo -S docker cp {nodes[node_name][1]}:/root/Results/{log_file} {temp_log_dir}/"
		logging.debug(f"Executing: {cmd}")
		output, err, fail = sshCmd(client, cmd)
		logging.debug(f"Exit code: {fail}")

	# Remove logs from E-VM
	for log_file in e_vm_log_files:
		cmd = f"sudo -S docker exec {nodes[node_name][1]} rm -f /root/Results/{log_file}"
		logging.debug(f"Executing: {cmd}")
		output, err, fail = sshCmd(client, cmd)
		logging.debug(f"Exit code: {fail}")

	# Copy logs from node to local machine
	for log_file in e_vm_log_files:
		transferFile(nodes[node_name][0], log_file, temp_log_dir, temp_log_dir)

	# Send logs from local machine to Kafka
	for log_file in os.listdir(f"{temp_log_dir}"):
		logging.debug(f"Sending {log_file} to Kafka")
		send_log_to_kafka(producer, temp_log_dir + "/" + log_file, params)

	# Remove logs from node
	cmd = f"sudo -S rm -rf {temp_log_dir}"
	logging.debug(f"Executing: {cmd}")
	output, err, fail = sshCmd(client, cmd)
	logging.debug(f"Exit code: {fail}")

	# Remove logs from local machine
	os.system(f"rm -rf {temp_log_dir}")
	# Note: client is now persistent and will be closed at the end of the script

def resetNode(client, ctnr):
	cmd = f"sudo -S rm -rf {temp_log_dir}"
	logging.debug(f"Executing: {cmd}")
	output, err, fail = sshCmd(client, cmd)
	logging.debug(f"Exit code: {fail}")

	cmd = f"sudo -S docker exec {ctnr} /root/stopexperiment.sh"
	logging.debug(f"Executing: {cmd}")
	output, err, fail = sshCmd(client, cmd)
	logging.debug(f"Exit code: {fail}")
	
	cmd = f"sudo -S docker exec {ctnr} ls /root/Results"
	logging.debug(f"Executing: {cmd}")
	output, err, fail = sshCmd(client, cmd)
	logging.debug(f"Exit code: {fail}")
	
	e_vm_log_files = output
	for log_file in e_vm_log_files.splitlines():
		cmd = f"sudo -S docker exec {ctnr} rm -f /root/Results/{log_file}"
		logging.debug(f"Executing: {cmd}")
		output, err, fail = sshCmd(client, cmd)
		logging.debug(f"Exit code: {fail}")


#**************************************************************
# Main
#-----
if __name__ == "__main__":
	# Set up command line parser
	parser = argparse.ArgumentParser(
		prog="Channel Sounder",
		description="Runs a channel sounder experiment to test reception between fixed nodes")
	parser.add_argument('-c', '--config', required=True, help="The config file for specifying the chains to test")
	
	# Setup logging
	time_start = datetime.now()
	script_name_noext = os.path.splitext(os.path.basename(sys.argv[0]))[0]
	logfile = logsdir + script_name_noext + ".log"
	try:
		open(logfile, 'a').close()
		logging.basicConfig(filename=logfile,filemode='a',format='[%(asctime)s.%(msecs)03d] [%(process)d] [%(levelname)s] %(message)s',datefmt='%Y-%m-%d %H:%M:%S',level=loglvl)
	except Exception as e:
		if os.isatty(sys.stdout.fileno()):
			# Fall back to stdout if log file unwriteable
			traceback.print_tb(e.__traceback__)
			print(f"[{script_name_noext}.py] Unable to open log file {logfile} for writing -- defaulting to stdout")
			logging.basicConfig(stream=sys.stdout,format='[%(asctime)s.%(msecs)03d] [%(process)d] [%(levelname)s] %(message)s',datefmt='%Y-%m-%d %H:%M:%S',level=logging.INFO)
		else:
			# Discard logs if nowhere to write to
			logname = "/dev/null"
			logging.basicConfig(filename=logfile,filemode='a',format='[%(asctime)s.%(msecs)03d] [%(process)d] [%(levelname)s] %(message)s',datefmt='%Y-%m-%d %H:%M:%S',level=loglvl)
	logging.info("Starting channel sounder experiments")

	args = parser.parse_args()
	try:
		with open(args.config, 'r') as config_file:
			pass
	except FileNotFoundError as e:
		logging.error(f"Config file {args.config} does not exist")
		sys.exit(1)
	logging.debug("Using config file: {args.config")
	
	# Initialize the Kafka producer
	try:
		producer = KafkaProducer(bootstrap_servers=KAFKA_SERVERS, value_serializer=lambda v: json.dumps(v).encode("utf-8"))
	except Exception as e:
		logging.error("Can't connect to Kafka")
		sys.exit(1)

	#1. Unpause containers and establish persistent connections
	workingnodes = []
	persistent_clients = {}  # Dictionary to store persistent SSH connections
	
	for nodename, [nodeip, ctnr] in nodes.items():
		client = connectTo(nodename, nodeip)
		if client is None:
			logging.error(f"{nodename}: Failed to connect -- Skipping node")
			continue
			
		state = getVMState(client, ctnr)
		if state == 'paused':
			logging.info(f"{nodename}: Container {ctnr} state {state} -- Unpausing")
			if pauseVM(client, ctnr, False):
				logging.info(f"{nodename}: {ctnr} unpaused")
				workingnodes.append([nodename, nodeip])
				persistent_clients[nodename] = client
			else:
				logging.warning(f"{nodename}: Failed -- Skipping node")
				client.close()
				continue
		elif state in ['created', 'running', 'exited']: #This should not really happen, but should be safe to proceed based on explanation of how AFRNs handle resources
			logging.warning(f"{nodename}: Container {ctnr} state {state}; Expected paused")
			if state != 'running':
				if startVM(client, ctnr):
					logging.info(f"{nodename}: Success")
					workingnodes.append([nodename, nodeip])
					persistent_clients[nodename] = client
				else:
					logging.warning(f"{nodename}: Failed -- Skipping node")
					client.close()
					continue
			else:
				workingnodes.append([nodename, nodeip])
				persistent_clients[nodename] = client
		else:   #This definitely needs someone to look at what is happening
			logging.error(f"{nodename}: Container {ctnr} state {state} -- Skipping node")
			client.close()
			continue

		if [nodename, nodeip] in workingnodes:
			resetNode(client, ctnr)

	# Clean up temp directory
	os.system(f"rm -rf {temp_log_dir}")

	# Read in test json and build tests
	with open(args.config, 'r') as file:
		data = json.load(file)

	for group in data["test_groups"]:
		group_name = group["group_name"]
		group_test_dur = group["test_duration"]
		transmitters = []
		receivers = []
		for chain in group["chains"]:
			# Add default gains if not specified in config
			if 'gain' not in chain:
				chain['gain'] = 76 if chain['transmission_type'] == 'TX' else 30
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


		logging.info("Test Group: " + group_name)
		logging.info("Transmitters: " + json.dumps(transmitters, indent=4))
		logging.info("Receiver Tests: " + json.dumps(receiver_tests, indent=4))

		# Add null transmitter for baseline test
		if group["run_control"] == "true":
			fake_transmitter = {
				"node_name": "null",
				"serial_number": "null",
				"channel": -1,
				"frequency": "null",
			}
			transmitters.insert(0, fake_transmitter)

		#2. Perform experiments
		for transmitter in transmitters:
			transmitter_name = transmitter['node_name']
			if transmitter_name == "null":
				transmitter_timestamp = time.strftime("%Y-%m-%d_%H_%M_%S")
			else:
				transmitter_ip = nodes[transmitter_name][0]
				transmitter_ctnr = nodes[transmitter_name][1]
				# start transmitting
				isTransmitting = False
				retries = 0
				while not isTransmitting and retries < 5:
					client = persistent_clients.get(transmitter_name)
					if client is None:
						logging.error(f"{transmitter_name}: No persistent connection available")
						break
					logging.info(f"{transmitter_name}: {transmitter_ctnr} starting transmitter {transmitter['serial_number']} channel {transmitter['channel']}")
					cmd = f"sudo -S docker exec {transmitter_ctnr} /root/startexperimentTX.sh {transmitter_name} {transmitter['serial_number']} {transmitter['frequency']} {transmitter['channel']} {transmitter['gain']}"
					logging.debug(f"Executing: {cmd}")
					output, err, fail = sshCmd(client, cmd)
					logging.debug(f"Exit code: {fail}")
					time.sleep(0.5)
					cmd = f"sudo -S docker exec {transmitter_ctnr} screen -ls | grep txGRC"
					logging.debug(f"Executing: {cmd}")
					output, err, fail = sshCmd(client, cmd)
					logging.debug(f"Exit code: {fail}")
					if output == "":
						logging.error(f"{transmitter_name}: Failed to start the transmitter -- Please check the container")
						retries += 1
					else:
						logging.info(f"{transmitter_name}: transmitting")
						isTransmitting = True
			for receiver_test in receiver_tests:
				receiver_counter = 0
				for receiver in receiver_test:
					if receiver["serial_number"] != transmitter["serial_number"]:
						receiver_name = receiver['node_name']
						receiver_ip = nodes[receiver_name][0]
						receiver_ctnr = nodes[receiver_name][1]
						# start receiver
						client = persistent_clients.get(receiver_name)
						if client is None:
							logging.error(f"{receiver_name}: No persistent connection available, skipping receiver")
							continue
						logging.info(f"{receiver_name}: {receiver_ctnr} starting receiver {receiver['serial_number']} channel {receiver['channel']}")
						cmd = f"sudo -S docker exec {receiver_ctnr} /root/startexperimentRX.sh {transmitter_name} {receiver_name} {receiver['serial_number']} {receiver['frequency']} {receiver['channel']} {receiver['gain']}"
						logging.debug(f"Executing: {cmd}")
						output, err, fail = sshCmd(client, cmd)
						logging.debug(f"Exit code: {fail}")
						cmd = f"sudo -S docker exec {receiver_ctnr} screen -ls | grep rxGRC"
						logging.debug(f"Executing: {cmd}")
						output, err, fail = sshCmd(client, cmd)
						logging.debug(f"Exit code: {fail}")
						if output == "":
							logging.error(f"{receiver_name}: Failed to start the receiver -- Please check the container")
						else:
							logging.info(f"{receiver_name}: receiving")
						receiver_counter += 1

				# There is a possibility that no receivers in the receiver_test were started for a transmitter.
				# In that case, don't wait.
				if receiver_counter != 0:
					# Approximate delay between running the start receiver command and the receiver actually starting
					offset_dur = 5
					time.sleep(group_test_dur + offset_dur)
				# stop receivers
				for receiver in receiver_test:
					if receiver["node_name"] != transmitter["node_name"]:
						receiver_name = receiver['node_name']
						receiver_ip = nodes[receiver_name][0]
						receiver_ctnr = nodes[receiver_name][1]
						client = persistent_clients.get(receiver_name)
						if client is None:
							logging.error(f"{receiver_name}: No persistent connection available")
							continue
						logging.info(f"{receiver_name}: {receiver_ctnr} stopping receiver")
						cmd1 = f"sudo -S docker exec {receiver_ctnr} /root/stopexperiment.sh"
						logging.debug(f"Executing: {cmd1}")
						output, err, fail = sshCmd(client, cmd1)
						logging.debug(f"Exit code: {fail}")
						if fail:
							logging.debug(f"Error: {err}, {output}")
				# Copy receiver logs and upload to Kafka
				for receiver in receiver_test:
					if receiver["serial_number"] != transmitter["serial_number"]:
						log_prefix = f"{transmitter['node_name']}:{receiver['node_name']}:{receiver['serial_number']}:{receiver['frequency']}:{receiver['channel']}"
						params = [log_prefix, transmitter['node_name'], transmitter['serial_number'], transmitter['channel'], transmitter['frequency'], receiver['node_name'], receiver['serial_number'], receiver['channel'], receiver['frequency']]
						client = persistent_clients.get(receiver["node_name"])
						if client:
							handler_upload_logs_to_kafka(client, receiver["node_name"], params, producer)
						else:
							logging.error(f"{receiver['node_name']}: No persistent connection available for log upload")

			# stop transmitter
			if transmitter_name != "null":
				logging.info(f"{transmitter_name}: {transmitter_ctnr} stopping transmitter")
				client = persistent_clients.get(transmitter_name)
				if client is None:
					logging.error(f"{transmitter_name}: No persistent connection available")
				else:
					cmd = f"sudo -S docker exec {transmitter_ctnr} /root/stopexperiment.sh"
					logging.debug(f"Executing: {cmd}")
					output, err, fail = sshCmd(client, cmd)
					logging.debug(f"Exit code: {fail}")
	
			# copy transmitter logs and upload to Kafka
			if transmitter_name == "null":
				params = [None, transmitter['node_name'], transmitter['serial_number'], transmitter['channel'], transmitter['frequency']]
				send_log_to_kafka(producer, f"{transmitter_timestamp}:radio_channelsoundertxgrc_log.txt", params)
			else:
				log_prefix = f"{transmitter['node_name']}:{transmitter['serial_number']}:{transmitter['frequency']}:{transmitter['channel']}"
				params = [log_prefix, transmitter['node_name'], transmitter['serial_number'], transmitter['channel'], transmitter['frequency']]
				client = persistent_clients.get(transmitter["node_name"])
				if client:
					handler_upload_logs_to_kafka(client, transmitter["node_name"], params, producer)
				else:
					logging.error(f"{transmitter['node_name']}: No persistent connection available for log upload")

	# Close all persistent SSH connections
	logging.info("Closing all persistent SSH connections")
	for nodename, client in persistent_clients.items():
		if client and client.get_transport():
			client.close()
			logging.debug(f"Closed connection to {nodename}")

	time_end = datetime.now()
	time_taken = time_end - time_start
	logging.info(f"Finished in {time_taken}")
	sys.exit(0)
