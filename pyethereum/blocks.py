import rlp
import re
from transactions import Transaction
from trie import Trie
from trie import DB
from trie import BLANK_NODE
from utils import big_endian_to_int as decode_int
from utils import int_to_big_endian as encode_int
from utils import sha3
from utils import STATEDB_DIR
from utils import recursive_int_to_big_endian
import utils
import os
import sys
import logging

logger = logging.getLogger(__name__)

ACCT_RLP_LENGTH = 4
NONCE_INDEX = 0
BALANCE_INDEX = 1
CODE_INDEX = 2
STORAGE_INDEX = 3


def cast_block_header_from_rlp_decoded(prevhash, uncles_root, coinbase, state,
                                       transactions_root, difficulty, timestamp, extradata, nonce):
    coinbase = coinbase.encode('hex')
    difficulty = decode_int(difficulty)
    timestamp = decode_int(timestamp)
    nonce = decode_int(nonce)
    return prevhash, uncles_root, coinbase, state, transactions_root, \
        difficulty, timestamp, extradata, nonce


class Block(object):

    def __init__(self, header, transaction_list, uncles, validate=True):
        self.reward = 10 ** 18
        self.gas_consumed = 0
        self.gaslimit = 1000000  # for now

        # FIXME: block header sent by PoC4.3 nodes has no "number"
        self.number = 0
        self.prevhash = header[0]
        self.uncles_root = header[1]
        self.coinbase = header[2]
        self.state = Trie(STATEDB_DIR, header[3])
        self.transactions_root = header[4]
        self.difficulty = header[5]
        self.timestamp = header[6]
        self.extradata = header[7]
        self.nonce = header[8]

        self.transactions = [Transaction(*x) for x in transaction_list]
        self.uncles = uncles

        logger.debug('New Block(%s)' % self.hash().encode('hex'))

        if validate is True:
            # Verifications
            if sha3(rlp.encode(recursive_int_to_big_endian(transaction_list))) != self.transactions_root:
                raise Exception("Transaction list root hash does not match!")
            if sha3(rlp.encode(self.uncles)) != self.uncles_root:
                raise Exception("Uncle root hash does not match!")
            if self.state.root != BLANK_NODE and self.state.db.get(self.state.root) == '':
                raise Exception("State Merkle root not found in database!")
            # TODO: check POW

    # get_index(bin or hex, int) -> bin
    def get_index(self, address, index):
        if len(address) == 40:
            address = address.decode('hex')
        acct = self.state.get(address) or ['', '', '', '']
        return acct[index]

    # set_index(bin or hex, int, bin)
    def set_index(self, address, index, value):
        if len(address) == 40:
            address = address.decode('hex')
        acct = self.state.get(address) or ['', '', '', '']
        acct[index] = value
        self.state.update(address, acct)

    # delta_index(bin or hex, int, int) -> success/fail
    def delta_index(self, address, index, value):
        if len(address) == 40:
            address = address.decode('hex')
        acct = self.state.get(address) or ['', '', '', '']
        if decode_int(acct[index]) + value < 0:
            return False
        acct[index] = encode_int(decode_int(acct[index]) + value)
        self.state.update(address, acct)
        return True

    def get_nonce(self, address):
        return decode_int(self.get_index(address, NONCE_INDEX))

    def increment_nonce(self, address):
        return self.delta_index(address, NONCE_INDEX, 1)

    def get_balance(self, address):
        return decode_int(self.get_index(address, BALANCE_INDEX))

    def set_balance(self, address, value):
        self.set_index(address, BALANCE_INDEX, encode_int(value))

    def delta_balance(self, address, value):
        return self.delta_index(address, BALANCE_INDEX, value)

    def get_code(self, address):
        codehash = self.get_index(address, CODE_INDEX)
        return self.state.db.get(codehash) if codehash else ''

    def set_code(self, address, value):
        self.state.db.put(sha3(value), value)
        self.state.db.commit()
        self.set_index(address, CODE_INDEX, sha3(value))

    def get_storage(self, address):
        return Trie(STATEDB_DIR, self.get_index(address, STORAGE_INDEX))

    def get_storage_data(self, address, index):
        t = self.get_storage(address)
        return decode_int(t.get(utils.coerce_to_bytes(index)))

    def set_storage_data(self, address, index, val):
        t = self.get_storage(address)
        if val:
            t.update(utils.coerce_to_bytes(index), encode_int(val))
        else:
            t.delete(utils.coerce_to_bytes(index))
        self.set_index(address, STORAGE_INDEX, t.root)

    def account_to_dict(self, address):
        if len(address) == 40:
            address = address.decode('hex')
        acct = self.state.get(address) or ['', '', '', '']
        chash = acct[CODE_INDEX]
        stdict = Trie(STATEDB_DIR, acct[STORAGE_INDEX]).to_dict(True)
        return {
            'nonce': decode_int(acct[NONCE_INDEX]),
            'balance': decode_int(acct[BALANCE_INDEX]),
            'code': self.state.db.get(chash).encode('hex') if chash else '',
            'storage': {decode_int(k): decode_int(stdict[k]) for k in stdict}
        }

    # Revert computation
    def snapshot(self):
        return {'state': self.state.root, 'gas': self.gas_consumed}

    def revert(self, mysnapshot):
        self.state.root = mysnapshot['state']
        self.gas_consumed = mysnapshot['gas']

    # Serialization method; should act as perfect inverse function of the
    # constructor assuming no verification failures
    def serialize(self):
        txlist = [x.serialize() for x in self.transactions]
        header = [encode_int(self.number),
                  self.prevhash,
                  sha3(rlp.encode(self.uncles)),
                  self.coinbase.decode('hex'),
                  self.state.root,
                  sha3(rlp.encode(txlist)),
                  encode_int(self.difficulty),
                  encode_int(self.timestamp),
                  self.extradata,
                  encode_int(self.nonce)]
        return rlp.encode([header, txlist, self.uncles])

    def to_dict(self):
        state = self.state.to_dict(True)
        nstate = {}
        for s in state:
            t = Trie(STATEDB_DIR, state[s][STORAGE_INDEX])
            o = [0] * ACCT_RLP_LENGTH
            o[NONCE_INDEX] = decode_int(state[s][NONCE_INDEX])
            o[BALANCE_INDEX] = decode_int(state[s][BALANCE_INDEX])
            o[CODE_INDEX] = state[s][CODE_INDEX]
            td = t.to_dict(True)
            o[STORAGE_INDEX] = {decode_int(k): decode_int(td[k]) for k in td}
            nstate[s.encode('hex')] = o

        return {
            "number": self.number,
            "prevhash": self.prevhash,
            "uncles_root": self.uncles_root,
            "coinbase": self.coinbase,
            "state": nstate,
            "transactions_root": self.transactions_root,
            "difficulty": self.difficulty,
            "timestamp": self.timestamp,
            "extradata": self.extradata,
            "nonce": self.nonce
        }

    def hash(self):
        return sha3(self.serialize())


def genesis(initial_alloc):
    header = ['', '', '0' * 40, BLANK_NODE, '', 2 ** 23, 0, '', 0]
    block = Block(header, transaction_list=[], uncles=[], validate=False)
    for addr in initial_alloc:
        block.set_balance(addr, initial_alloc[addr])
    return block
