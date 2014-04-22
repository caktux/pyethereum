import logging
import time
from dispatch import receiver
from blocks import Block
from common import StoppableLoopThread
from trie import rlp_hash, rlp_hash_hex
import transactions
import signals

logger = logging.getLogger(__name__)


class ChainManager(StoppableLoopThread):

    """
    Manages the chain and requests to it.
    """

    def __init__(self):
        super(ChainManager, self).__init__()
        self.transactions = set()
        self.dummy_blockchain = dict()  # hash > block

    def configure(self, config):
        self.config = config

    def bootstrap_blockchain(self):
        # genesis block
        # http://etherchain.org/#/block/
        # ab6b9a5613970faa771b12d449b2e9bb925ab7a369f0a4b86b286e9d540099cf
        if len(self.dummy_blockchain):
            return
        genesis_H = 'ab6b9a5613970faa771b12d449b2e9bb925ab7a369f'\
            '0a4b86b286e9d540099cf'.decode('hex')
        signals.remote_chain_data_requested.send(
            sender=self, parents=[genesis_H], count=100)

    def loop_body(self):
        self.mine()
        self.bootstrap_blockchain()
        time.sleep(10)

    def mine(self):
        "in the meanwhile mine a bit, not efficient though"
        pass

    def recv_blocks(self, blocks):

        with self.lock:
            ct = transactions.cast_transaction_args_from_rlp_decoded
            ch = blocks.cast_block_header_from_rlp_decoded
            blocks = [Block(ch(*header), [ct(*t) for t in transaction_list], uncles)
                      for header, transaction_list, uncles in blocks]

            # store block
            for block in blocks:
                h = block.hash()
                if h not in self.dummy_blockchain:
                    logger.debug("received new block: %s", h)
                    self.dummy_blockchain[h] = block
                else:
                    logger.debug("received known block: %s", h)

            # check for children
            prev_hashes = set(
                b.prevhash for b in self.dummy_blockchain.values())
            for b in blocks:
                if b.hash() not in prev_hashes:
                    logger.debug("block w/o child: %s", b.hash())
                    signals.remote_chain_data_requested.send(
                        sender=self, parents=[h], count=1)

            logger.debug('known blocks:%d', len(self.dummy_blockchain))

    def add_transactions(self, transactions):
        logger.debug("add transactions %r", transactions)
        for tx in tx_list:
            self.transactions.add(tx)

    def get_transactions(self):
        logger.debug("get transactions")
        return self.transactions

chain_manager = ChainManager()


@receiver(signals.config_ready)
def config_chainmanager(sender, **kwargs):
    chain_manager.configure(sender)


@receiver(signals.new_transactions_received)
def new_transactions_received_handler(sender, transactions, **kwargs):
    chain_manager.add_transactions(transactions)


@receiver(signals.transactions_data_requested)
def transactions_data_requested_handler(sender, **kwargs):
    transactions = chain_manager.get_transactions()


@receiver(signals.blocks_data_requested)
def blocks_data_requested_handler(sender, request_data, **kwargs):
    pass


@receiver(signals.new_blocks_received)
def new_blocks_received_handler(sender, blocks, **kwargs):
    logger.debug("received blocks: %r", [rlp_hash_hex(b) for b in blocks])
    chain_manager.recv_blocks(blocks)
