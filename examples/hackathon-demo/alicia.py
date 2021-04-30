import datetime
import json
import os
import random
import shutil
import subprocess
import time

import maya

from nucypher.characters.lawful import Bob, Ursula, Enrico
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.logging import GlobalLoggerSettings

GlobalLoggerSettings.start_console_logging()
TEMP_ALICE_DIR = os.path.join('/', 'tmp', 'hackathon')
FAKE_S3_FOLDER = os.path.join(TEMP_ALICE_DIR, 's3')
ENCRYPTED_HEARTBEAT = os.path.join(FAKE_S3_FOLDER, "alice_heart_beat.enc")
DATA_POLICY_KEY = os.path.join(FAKE_S3_FOLDER, "heartbeat_policy.pub")
HEARTBEAT = "alice_heart_beat.json"
SEEDNODE_URI = "localhost:11500"
POLICY_FILENAME = "policy-metadata.json"
passphrase = "TEST_ALICIA_INSECURE_DEVELOPMENT_PASSWORD"

shutil.rmtree(TEMP_ALICE_DIR, ignore_errors=True)

ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URI, federated_only=True, minimum_stake=0)

alice_config = AliceConfiguration(
    config_root=os.path.join(TEMP_ALICE_DIR),
    domain=TEMPORARY_DOMAIN,
    known_nodes={ursula},
    start_learning_now=False,
    federated_only=True,
    learn_on_same_thread=True,
)
alice_config.initialize(password=passphrase)

print("Alice has been initialized")
subprocess.run(["tree", TEMP_ALICE_DIR])
input("Continue\n")

alice_config.keyring.unlock(password=passphrase)
print("Alice Key Unlocked - ready to encrypt")
input("Continue\n")

alicia = alice_config.produce()
alice_config_file = alice_config.to_configuration_file()
print("Alice Config saved")
subprocess.run(["ccat", "/tmp/hackathon/alice.json"])
subprocess.run(["echo", "\r"])
subprocess.run(["tree", TEMP_ALICE_DIR])
input("Alice has Ursula Seed TLS")

alicia.start_learning_loop(now=True)
subprocess.run(["tree", "/tmp/hackathon/known_nodes"])
input("Alicia Knows about the Ursula Network")

label = str.encode("heart-data-label")
print("Label generated for IOT data: ", label)

policy_pubkey = alicia.get_policy_encrypting_key_from_label(label)
encrico = Enrico(policy_encrypting_key=policy_pubkey)
enrico_public_key = bytes(encrico.stamp)
input("Enrico set up to accept Data for Encryption, Time to generate heart-rate data.")

heart_rate = 80
now = time.time()
beats = list()

for _ in range(50):
    heart_rate = random.randint(max(60, heart_rate - 5), min(100, heart_rate + 5))
    now += 3

    beats.append({
        'heart_rate': heart_rate,
        'timestamp': now,
    })


data = {'heartbeats': beats}

with open(HEARTBEAT, 'w') as outfile:
    json.dump(data, outfile)

subprocess.run(["jq", ".", HEARTBEAT])
input("Time to encrypt message")

with open(HEARTBEAT, 'rb') as file:
    plain_bytes = file.read()
    encrypted_msg, _signature = encrico.encrypt_message(plain_bytes)

if not os.path.exists(FAKE_S3_FOLDER):
    os.makedirs(FAKE_S3_FOLDER)

with open(ENCRYPTED_HEARTBEAT, 'wb') as enc_out:
    enc_out.write(encrypted_msg.to_bytes())

with open(DATA_POLICY_KEY, 'wb') as policy_out:
    policy_out.write(enrico_public_key)

subprocess.run(["tree", TEMP_ALICE_DIR])

input("Read Encrypted Message")
subprocess.run(["ccat", ENCRYPTED_HEARTBEAT])
subprocess.run(["echo", "\r"])

input("Read Policy File")
subprocess.run(["ccat", DATA_POLICY_KEY])
subprocess.run(["echo", "\r"])

from doctor_keys import get_doctor_pubkeys, DOCTOR_PUBLIC_JSON, DOCTOR_PRIVATE_JSON

doctor_pubkeys = get_doctor_pubkeys()

input("Doctor Public Key")
subprocess.run(["jq", ".", DOCTOR_PUBLIC_JSON])
input("Doctor Private Key")
subprocess.run(["jq", ".", DOCTOR_PRIVATE_JSON])


doctor_strange = Bob.from_public_keys(
    verifying_key=doctor_pubkeys['sig'],
    encrypting_key=doctor_pubkeys['enc'],
    federated_only=True)

# Here are our remaining Policy details, such as:
# - Policy expiration date
policy_end_datetime = maya.now() + datetime.timedelta(days=1)
# - m-out-of-n: This means Alicia splits the re-encryption key in 5 pieces and
#               she requires Bob to seek collaboration of at least 3 Ursulas
m, n = 2, 3


# With this information, Alicia creates a policy granting access to Bob.
# The policy is sent to the NuCypher network.
input("Alice creates an access policy for the Doc")
policy = alicia.grant(bob=doctor_strange, label=label, m=m, n=n, expiration=policy_end_datetime)
policy.treasure_map_publisher.block_until_complete()

# For the demo, we need a way to share with Bob some additional info
# about the policy, so we store it in a JSON file
policy_info = {
    "policy_pubkey": policy.public_key.to_bytes().hex(),
    "alice_sig_pubkey": bytes(alicia.stamp).hex(),
    "label": label.decode("utf-8"),
}

with open(POLICY_FILENAME, 'w') as f:
    json.dump(policy_info, f)

input("Read Policy file")
subprocess.run(["jq", ".", POLICY_FILENAME])

input("Doctor has now access to data")
answer = input("Revoke policy? (y/N): ")

if answer == "y"  or answer == "Y" or answer == "yes" or answer == "Yes":
    result = alicia.revoke(policy=policy)
    print("Policy revoked. Doctor can no longer decrypt data")
