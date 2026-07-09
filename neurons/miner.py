"""FaultLine miner: serves boundary cases from ./seed_cases (rotating queue).
Day-1: your handcrafted seeds ARE the mining strategy. Automate generation later.

Run:
python neurons/miner.py --netuid <NETUID> --subtensor.network test \
    --wallet.name miner --wallet.hotkey default --axon.port 8091 --logging.debug
"""
import json
import os
import pathlib
import time
import itertools
import bittensor as bt
from protocol import CaseSynapse

def get_config():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int)
    bt.Subtensor.add_args(parser)
    bt.Wallet.add_args(parser)
    bt.Axon.add_args(parser)
    bt.logging.add_args(parser)
    os.environ.setdefault("BT_NO_PARSE_CLI_ARGS", "false")
    config = bt.Config(parser)
    if config.netuid is None:
        parser.error("--netuid is required")
    return config

def main():
    config = get_config()
    bt.logging.set_config(config)
    wallet = bt.Wallet(config=config)
    subtensor = bt.Subtensor(config=config)
    metagraph = subtensor.metagraph(config.netuid)
    if wallet.hotkey.ss58_address not in metagraph.hotkeys:
        bt.logging.error("Hotkey not registered on netuid. Run btcli subnet register first.")
        return

    cases = [json.loads(p.read_text())
             for p in sorted(pathlib.Path(__file__).parent.parent.joinpath("seed_cases").glob("*.json"))]
    queue = itertools.cycle(cases)
    bt.logging.info(f"Loaded {len(cases)} cases into rotation.")

    def forward(synapse: CaseSynapse) -> CaseSynapse:
        synapse.case_json = json.dumps(next(queue))
        return synapse

    axon = bt.Axon(wallet=wallet, config=config)
    axon.attach(forward_fn=forward)
    axon.serve(netuid=config.netuid, subtensor=subtensor)
    axon.start()
    bt.logging.info(f"Miner axon serving on port {config.axon.port}.")
    while True:
        time.sleep(30)

if __name__ == "__main__":
    main()
