#!/usr/bin/python
import processblock
import transactions
import blocks
import utils
import trie
import rlp


def sha3(x):
    return utils.sha3(x).encode('hex')


def privtoaddr(x):
    if len(x) == 64:
        x = x.decode('hex')
    return utils.privtoaddr(x)

def block_from_hexdata(hexdata):
    header, transaction_list, uncles = rlp.decode(hexdata.decode('hex'))
    header = blocks.cast_block_header_from_rlp_decoded(*header)
    return blocks.Block(header, transaction_list, uncles)

def transaction_from_hexdata(hexdata):
    return transactions.transaction_from_rlp_encoded(hexdata.decode('hex'))

def mkgenesis(*args):
    if len(args) == 2 and ':' not in args[0]:
        return blocks.genesis({args[0]: int(args[1])}).serialize().encode('hex')
    else:
        o = {}
        for a in args:
            o[a[:a.find(':')]] = int(a[a.find(':')+1:])
        return blocks.genesis(o).serialize().encode('hex')


def mktx(nonce, value, to, data):
    return transactions.Transaction(int(nonce), int(value), 10 ** 12, 10000, to, data.decode('hex')).serialize(False).encode('hex')


def mkcontract(nonce, value, code):
    return transactions.contract(int(nonce), int(value), 10 ** 12, 10000, code.decode('hex')).serialize(False).encode('hex')


def sign(txdata, key):
    return transaction_from_hexdata(txdata).sign(key).serialize(True).encode('hex')

def alloc(blockdata, addr, val):
    val = int(val)
    block = block_from_hexdata(blockdata)
    block.delta_balance(addr,val)
    return block.serialize().encode('hex')

def applytx(blockdata, txdata, debug=0, limit=2**100):
    block = block_from_hexdata(blockdata)
    tx = transaction_from_hexdata(txdata)
    if tx.startgas > limit:
        raise Exception("Transaction is asking for too much gas!")
    if debug:
        processblock.debug = 1
    o = processblock.apply_tx(block, tx)
    return block.serialize().encode('hex'), ''.join(o).encode('hex')


def getbalance(blockdata, address):
    block = block_from_hexdata(blockdata)
    return block.get_balance(address)

def getcode(blockdata, address):
    block = block_from_hexdata(blockdata)
    return block.get_code(address).encode('hex')

def getstate(blockdata, address=None):
    block = block_from_hexdata(blockdata)
    if not address:
        return block.to_dict()
    else:
        return block.get_storage(address).to_dict()

def account_to_dict(blockdata, address):
    block = block_from_hexdata(blockdata)
    return block.account_to_dict(address)


def dbget(x):
    db = trie.DB('statedb')
    print db.get(x.decode('hex'))
