import re
import rlp
from bitcoin import encode_pubkey
from bitcoin import ecdsa_raw_sign, ecdsa_raw_recover
from opcodes import reverse_opcodes
from utils import big_endian_to_int
from utils import int_to_big_endian
from utils import sha3, privtoaddr
import utils
import sys


class Transaction(object):

    """
    A transaction is stored as:
    [ nonce, value, gasprice, startgas, to, data, v, r, s]
    nonce is the number of transactions already sent by that account,
    encoded in binary form (eg. 0 -> '', 7 -> '\x07', 1000 -> '\x03\xd8').
    (v,r,s) is the raw Electrum-style signature of the transaction without the signature
    made with the private key corresponding to the sending account, with 0 <= v <= 3.
    From an Electrum-style signature (65 bytes) it is possible to extract the public key,
    and thereby the address, directly. A valid transaction is one where
    (i) the signature is well-formed (ie. 0 <= v <= 3, 0 <= r < P, 0 <= s < N, 0 <= r < P - N if v >= 2), and
    (ii) the sending account has enough funds to pay the fee and the value.
    """
    # nonce,value,gasprice,startgas,to,data

    def __init__(self, nonce, value, gasprice, startgas, to, data, v=0, r=0, s=0):
        self.nonce = int(nonce)
        self.value = int(value)
        self.gasprice = int(gasprice)
        self.startgas = int(startgas)
        self.to = utils.coerce_addr_to_bin(to)
        self.data = data
        self.v, self.r, self.s = int(v), int(r), int(s)

        self.sender = 0

        # includes signature
        if self.r > 0 and self.s > 0:
            rawhash = self.serialize(False)
            pub = encode_pubkey(
                ecdsa_raw_recover(rawhash, (self.v, self.r, self.s)), 'bin')
            self.sender = sha3(pub[1:])[-20:].encode('hex')

    def sign(self, key):
        rawhash = sha3(rlp.encode(self.serialize(False)))
        self.v, self.r, self.s = ecdsa_raw_sign(rawhash, key)
        self.sender = privtoaddr(key)
        return self

    def coerce_to_hex(self, n):
        return n.encode('hex') if len(n) == 20 else n

    def serialize(self, signed=True):
        return rlp.encode([int_to_big_endian(self.nonce),
                           int_to_big_endian(self.value),
                           int_to_big_endian(self.gasprice),
                           int_to_big_endian(self.startgas),
                           utils.coerce_addr_to_bin(self.to),
                           self.data,
                           int_to_big_endian(self.v),
                           int_to_big_endian(self.r),
                           int_to_big_endian(self.s)][:9 if signed else 6])

    def hex_serialize(self):
        return self.serialize().encode('hex')

    def hash(self):
        return sha3(self.serialize())


def contract(nonce, endowment, gasprice, startgas, code, v=0, r=0, s=0):
    tx = Transaction(nonce, endowment, gasprice, startgas, '', code)
    tx.v, tx.r, tx.s = v, r, s
    return tx


def cast_transaction_args_from_rlp_decoded(nonce, value, gasprice, startgas, to, data, v=0, r=0, s=0):
    "rlp encoding is not aware of types"
    d = big_endian_to_int
    return [d(nonce), d(value), d(gasprice), d(startgas), to.encode('hex'), data, d(v), d(r), d(s)]


def transaction_from_rlp_encoded(data):
    return Transaction(cast_transaction_args_from_rlp_decoded(rlp.decode(data)))
