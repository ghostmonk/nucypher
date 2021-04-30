import json
import os
import shutil
import subprocess

from nucypher.characters.lawful import Bob, Enrico, Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.keypairs import DecryptingKeypair, SigningKeypair
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import GlobalLoggerSettings
from umbral.keys import UmbralPrivateKey, UmbralPublicKey


GlobalLoggerSettings.start_console_logging()

SEEDNODE_URI = "localhost:11500"
TEMP_DOCTOR_DIR = "{}/doctor-files".format(os.path.dirname(os.path.abspath(__file__)))

# Remove previous demo files and create new ones
shutil.rmtree(TEMP_DOCTOR_DIR, ignore_errors=True)

ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URI, federated_only=True, minimum_stake=0)

# To create a Bob, we need the doctor's private keys previously generated.
DOCTOR_PUBLIC_JSON = 'doctor.public.json'
DOCTOR_PRIVATE_JSON = 'doctor.private.json'

TEMP_ALICE_DIR = os.path.join('/', 'tmp', 'hackathon')
FAKE_S3_FOLDER = os.path.join(TEMP_ALICE_DIR, 's3')
ENCRYPTED_HEARTBEAT = os.path.join(FAKE_S3_FOLDER, "alice_heart_beat.enc")
DATA_POLICY_KEY = os.path.join(FAKE_S3_FOLDER, "heartbeat_policy.pub")


def generate_doctor_keys():
    enc_privkey = UmbralPrivateKey.gen_key()
    sig_privkey = UmbralPrivateKey.gen_key()

    doctor_privkeys = {
        'enc': enc_privkey.to_bytes().hex(),
        'sig': sig_privkey.to_bytes().hex(),
    }

    with open(DOCTOR_PRIVATE_JSON, 'w') as f:
        json.dump(doctor_privkeys, f)

    enc_pubkey = enc_privkey.get_pubkey()
    sig_pubkey = sig_privkey.get_pubkey()
    doctor_pubkeys = {
        'enc': enc_pubkey.to_bytes().hex(),
        'sig': sig_pubkey.to_bytes().hex()
    }
    with open(DOCTOR_PUBLIC_JSON, 'w') as f:
        json.dump(doctor_pubkeys, f)


def _get_keys(file, key_class):
    if not os.path.isfile(file):
        generate_doctor_keys()

    with open(file) as f:
        stored_keys = json.load(f)
    keys = dict()
    for key_type, key_str in stored_keys.items():
        keys[key_type] = key_class.from_bytes(bytes.fromhex(key_str))
    return keys


def get_doctor_pubkeys():
    return _get_keys(DOCTOR_PUBLIC_JSON, UmbralPublicKey)


def get_doctor_privkeys():
    return _get_keys(DOCTOR_PRIVATE_JSON, UmbralPrivateKey)

doctor_keys = get_doctor_privkeys()

bob_enc_keypair = DecryptingKeypair(private_key=doctor_keys["enc"])
bob_sig_keypair = SigningKeypair(private_key=doctor_keys["sig"])
enc_power = DecryptingPower(keypair=bob_enc_keypair)
sig_power = SigningPower(keypair=bob_sig_keypair)
power_ups = [enc_power, sig_power]

doctor = Bob(
    domain=TEMPORARY_DOMAIN,
    federated_only=True,
    crypto_power_ups=power_ups,
    start_learning_now=True,
    abort_on_learning_error=True,
    known_nodes=[ursula],
    save_metadata=False,
    network_middleware=RestMiddleware(),
)

print("Doctor = ", doctor)
input("Load policy data")

with open("policy-metadata.json", 'r') as f:
    policy_data = json.load(f)

policy_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data["policy_pubkey"]))
alices_sig_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data["alice_sig_pubkey"]))
label = policy_data["label"].encode()

doctor.join_policy(label, alices_sig_pubkey)
print("Policy for label '{}' loaded".format(label.decode("utf-8")))

input("Load encrypted Data from: " + ENCRYPTED_HEARTBEAT)
with open(ENCRYPTED_HEARTBEAT, 'rb') as file:
    plain_bytes = file.read()

with open(DATA_POLICY_KEY, 'rb') as file:
    data_policy = file.read()

data_source = Enrico.from_public_keys(
    verifying_key=data_policy,
    policy_encrypting_key=policy_pubkey
)

input("Ask Ursula network to proxy re-encrypt to Doctors public keys and print")
retrieved = doctor.retrieve(
    UmbralMessageKit.from_bytes(plain_bytes),
    label=label,
    enrico=data_source,
    alice_verifying_key=alices_sig_pubkey)

result = json.loads(retrieved[0].decode())
print(json.dumps(result, indent=2))
