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


def print_roman(text):
    subprocess.run(["figlet", "-f", "roman", "-w", "120", text])
    input("Continue\n")


print_roman("Alice initialized")
subprocess.run(["tree", TEMP_ALICE_DIR])
input("Continue\n")

alice_config.keyring.unlock(password=passphrase)

print_roman("Key Unlocked: Ready to encrypt")

alicia = alice_config.produce()
alice_config_file = alice_config.to_configuration_file()
print_roman("Config saved")
subprocess.run(["ccat", "/tmp/hackathon/alice.json"])
input("Continue\n")

print_roman("Ursula Seed Known")
subprocess.run(["tree", TEMP_ALICE_DIR])
input("Continue\n")

alicia.start_learning_loop(now=True)
print_roman("Ursula Network Available")
subprocess.run(["tree", "/tmp/hackathon/known_nodes"])
input("Continue\n")

label = str.encode("heart-data-label")
print_roman("Label:" + label.decode())

policy_pubkey = alicia.get_policy_encrypting_key_from_label(label)
encrico = Enrico(policy_encrypting_key=policy_pubkey)
enrico_public_key = bytes(encrico.stamp)
print_roman("Enrico Ready: Gen heartbeat data.")

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
print_roman("Encrypt message")

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

print_roman("Read Encrypted Message")
subprocess.run(["ccat", ENCRYPTED_HEARTBEAT])
subprocess.run(["echo", "\r"])

print_roman("Read Policy File")
subprocess.run(["ccat", DATA_POLICY_KEY])
subprocess.run(["echo", "\r"])

from doctor_keys import get_doctor_pubkeys, DOCTOR_PUBLIC_JSON, DOCTOR_PRIVATE_JSON

doctor_pubkeys = get_doctor_pubkeys()

print_roman("Doctor Public Key")
subprocess.run(["jq", ".", DOCTOR_PUBLIC_JSON])
print_roman("Doctor Private Key")
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
print_roman("Doc Policy Creation")
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

print_roman("Read Policy file")
subprocess.run(["jq", ".", POLICY_FILENAME])

input("Doctor has now access to data")
answer = input("Revoke policy? (y/N): ")

if answer == "y"  or answer == "Y" or answer == "yes" or answer == "Yes":
    result = alicia.revoke(policy=policy)
    print("Policy revoked. Doctor can no longer decrypt data")
