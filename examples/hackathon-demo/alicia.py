import datetime
import json
import os
import random
import shutil
import subprocess
import time

import maya
import msgpack

from nucypher.characters.lawful import Bob, Ursula, Enrico
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.logging import GlobalLoggerSettings

GlobalLoggerSettings.start_console_logging()
TEMP_ALICE_DIR = os.path.join('/', 'tmp', 'hackathon')
SEEDNODE_URI = "localhost:11500"
POLICY_FILENAME = "policy-metadata.json"
passphrase = "TEST_ALICIA_INSECURE_DEVELOPMENT_PASSWORD"
HEART_DATA_FILENAME = 'heart_data.msgpack'

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
subprocess.run(["tree", "/tmp/hackathon"])
input("Continue")

alice_config.keyring.unlock(password=passphrase)
print("Alice Key Unlocked - ready to encrypt")
input("Continue")

alicia = alice_config.produce()
alice_config_file = alice_config.to_configuration_file()
print("Alice Config saved")
subprocess.run(["ccat", "/tmp/hackathon/alice.json"])
subprocess.run(["echo", "\r"])
subprocess.run(["tree", "/tmp/hackathon"])
input("Alice has Ursula Seed TLS")

alicia.start_learning_loop(now=True)
subprocess.run(["tree", "/tmp/hackathon/known_nodes"])
input("Alicia Knows about the Ursula Network")

label = "heart-data-❤️-"+os.urandom(4).hex()
print("Label generated for IOT data: ", label)
label = label.encode()
print("Label encoded: ", label)

policy_pubkey = alicia.get_policy_encrypting_key_from_label(label)
data_source = Enrico(policy_encrypting_key=policy_pubkey)
data_source_public_key = bytes(data_source.stamp)
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


data = {
    'heartbeats': beats,
}

with open('alice_heart_data.json', 'w') as outfile:
    json.dump(data, outfile)

subprocess.run(["jq", ".", "alice_heart_data.json"])

with open('alice_heart_data.json', 'rb') as file:
    plain_bytes = file.read()
    encrypted_msg, _signature = data_source.encrypt_message(plain_bytes)

with open('alice_heart_data.enc', 'wb') as enc_out:
    enc_out.write(encrypted_msg.to_bytes())

subprocess.run(["ccat", "alice_heart_data.enc"])

input("Continue")

from doctor_keys import get_doctor_pubkeys
doctor_pubkeys = get_doctor_pubkeys()
print("Doctor Public keys generated")

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
print("Creating access policy for the Doctor...")
policy = alicia.grant(bob=doctor_strange,
                      label=label,
                      m=m,
                      n=n,
                      expiration=policy_end_datetime)
policy.treasure_map_publisher.block_until_complete()
print("Done!")

# For the demo, we need a way to share with Bob some additional info
# about the policy, so we store it in a JSON file
policy_info = {
    "policy_pubkey": policy.public_key.to_bytes().hex(),
    "alice_sig_pubkey": bytes(alicia.stamp).hex(),
    "label": label.decode("utf-8"),
}

filename = POLICY_FILENAME
with open(filename, 'w') as f:
    json.dump(policy_info, f)
