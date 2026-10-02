"""Pure-Python RSA (PKCS#1 v1.5, SHA-256) with a seeded, deterministic keygen.

TEST ONLY. Keys are derived from a public seed so the whole synthetic corpus,
test CA included, regenerates bit-for-bit. Anyone who knows the seed knows
every private key: never use these keys, or this code, outside the proof pack.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

# DigestInfo prefix for SHA-256 (RFC 8017, section 9.2 note 1)
_SHA256_DI = bytes.fromhex("3031300d060960864801650304020105000420")

_SMALL_PRIMES = []
_sieve = bytearray([1]) * 3000
for _i in range(2, 3000):
    if _sieve[_i]:
        _SMALL_PRIMES.append(_i)
        for _j in range(_i * _i, 3000, _i):
            _sieve[_j] = 0
del _sieve


class Drbg:
    """SHA-256 counter-mode byte stream. Deterministic; not a CSPRNG for real use."""

    def __init__(self, seed: bytes):
        self._seed = hashlib.sha256(seed).digest()
        self._ctr = 0

    def read(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n:
            out += hashlib.sha256(self._seed + self._ctr.to_bytes(8, "big")).digest()
            self._ctr += 1
        return bytes(out[:n])

    def below(self, n: int) -> int:
        k = (n.bit_length() + 7) // 8 + 8
        return int.from_bytes(self.read(k), "big") % n


def _is_probable_prime(n: int, drbg: Drbg, rounds: int = 24) -> bool:
    if n < 2:
        return False
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = 2 + drbg.below(n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int, drbg: Drbg, e: int) -> int:
    c = int.from_bytes(drbg.read(bits // 8), "big")
    c |= (1 << (bits - 1)) | (1 << (bits - 2)) | 1
    while True:
        if (c - 1) % e != 0 and _is_probable_prime(c, drbg):
            return c
        c += 2


@dataclass(frozen=True)
class PublicKey:
    n: int
    e: int

    @property
    def size_bytes(self) -> int:
        return (self.n.bit_length() + 7) // 8


@dataclass(frozen=True)
class PrivateKey:
    n: int
    e: int
    d: int
    p: int
    q: int

    @property
    def public(self) -> PublicKey:
        return PublicKey(self.n, self.e)


def generate(label: str, seed: int, bits: int = 2048, e: int = 65537) -> PrivateKey:
    drbg = Drbg(f"costanza-notari-v2|TEST-ONLY|{seed}|{label}".encode())
    while True:
        p = _gen_prime(bits // 2, drbg, e)
        q = _gen_prime(bits // 2, drbg, e)
        if p != q and (p * q).bit_length() == bits:
            break
    phi = (p - 1) * (q - 1)
    d = pow(e, -1, phi)
    return PrivateKey(p * q, e, d, p, q)


def _emsa_pkcs1_v15(message: bytes, k: int) -> bytes:
    t = _SHA256_DI + hashlib.sha256(message).digest()
    if k < len(t) + 11:
        raise ValueError("key too short")
    return b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t


def sign(key: PrivateKey, message: bytes) -> bytes:
    k = (key.n.bit_length() + 7) // 8
    m = int.from_bytes(_emsa_pkcs1_v15(message, k), "big")
    # CRT
    dp, dq = key.d % (key.p - 1), key.d % (key.q - 1)
    qinv = pow(key.q, -1, key.p)
    m1, m2 = pow(m, dp, key.p), pow(m, dq, key.q)
    h = (qinv * (m1 - m2)) % key.p
    s = m2 + h * key.q
    return s.to_bytes(k, "big")


def verify(pub: PublicKey, message: bytes, signature: bytes) -> bool:
    """Strict verification: re-encode EMSA and compare byte-for-byte."""
    k = pub.size_bytes
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= pub.n:
        return False
    em = pow(s, pub.e, pub.n).to_bytes(k, "big")
    try:
        return em == _emsa_pkcs1_v15(message, k)
    except ValueError:
        return False


# ------------------------------------------------------------ PKCS#8 export
def private_key_pkcs1_der(key: PrivateKey) -> bytes:
    from . import der
    dp, dq = key.d % (key.p - 1), key.d % (key.q - 1)
    qinv = pow(key.q, -1, key.p)
    return der.seq(der.integer(0), der.integer(key.n), der.integer(key.e), der.integer(key.d),
                   der.integer(key.p), der.integer(key.q), der.integer(dp), der.integer(dq),
                   der.integer(qinv))


def private_key_pkcs8_der(key: PrivateKey) -> bytes:
    from . import der
    alg = der.seq(der.oid("1.2.840.113549.1.1.1"), der.null())
    return der.seq(der.integer(0), alg, der.octet_string(private_key_pkcs1_der(key)))
