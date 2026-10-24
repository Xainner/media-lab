#!/usr/bin/env python3
"""Provision ONLY new secrets/certificates; never overwrite or import old state."""
import argparse
import datetime as dt
import os
import secrets
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--host", required=True, help="the public host name, e.g. media.example.com")
args = parser.parse_args()
directory = args.directory.resolve()
if directory.exists():
    raise SystemExit("Refusing to overwrite an existing secrets directory")
if directory == Path.home() or directory == Path("/"):
    raise SystemExit("Use a dedicated secrets directory outside the repository")
os.umask(0o077)
directory.mkdir(parents=True, mode=0o700)
now = dt.datetime.now(dt.timezone.utc)
ca_key, leaf_key = rsa.generate_private_key(65537, 3072), rsa.generate_private_key(65537, 3072)
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Media Lab Origin CA")])
ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
      .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
      .not_valid_after(now + dt.timedelta(days=365 * 5))
      .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
      .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                     data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                     encipher_only=False, decipher_only=False), critical=True).sign(ca_key, hashes.SHA256()))
leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, args.host)]))
        .issuer_name(ca_name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(args.host), x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256()))
for name, value in (("origin-ca.key", ca_key), ("origin.key", leaf_key)):
    (directory / name).write_bytes(value.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
for name, value in (("origin-ca.crt", ca), ("origin.crt", leaf)):
    (directory / name).write_bytes(value.public_bytes(serialization.Encoding.PEM))
for name in ("master.key", "agent.key"):
    (directory / name).write_bytes(secrets.token_bytes(32))
print("Provisioned dedicated secrets (0700/0600); only origin-ca.crt may be copied to NPM.")
print("Origin certificate expires:", leaf.not_valid_after_utc.isoformat())
