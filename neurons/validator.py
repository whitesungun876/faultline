"""FaultLine validator: query miners for cases -> validity gate + scoring -> EMA -> set_weights.

Backend selection:
  --mock_backend        scripted naive agent (no GPU; for wiring tests ONLY)
  default               HFBackend pinned model (needs GPU/CPU with transformers + HF access)

Run:
python neurons/validator.py --netuid <NETUID> --subtensor.network test \
    --wallet.name validator --wallet.hotkey default --mock_backend --logging.debug
"""
import json
import os
import pathlib
import sys
import time
import uuid
import numpy as np
import bittensor as bt
from protocol import CaseSynapse

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from faultline.verify import evaluate_case          # noqa: E402
from faultline.harness import ScriptedBackend        # noqa: E402

CORPUS_PATH = pathlib.Path("corpus_index.json")
EMA_ALPHA = 0.2
QUERY_PERIOD_S = 60

def get_config():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--netuid", type=int)
    parser.add_argument("--mock_backend", action="store_true")
    bt.Subtensor.add_args(parser)
    bt.Wallet.add_args(parser)
    bt.logging.add_args(parser)
    os.environ.setdefault("BT_NO_PARSE_CLI_ARGS", "false")
    config = bt.Config(parser)
    if config.netuid is None:
        parser.error("--netuid is required")
    return config

def load_backend(config):
    if config.mock_backend:
        return lambda: ScriptedBackend(['{"finish": "done"}'])
    from faultline.harness import HFBackend
    backend = HFBackend()          # pinned model = the v0 target registry
    return lambda: backend

def main():
    config = get_config()
    bt.logging.set_config(config)
    wallet = bt.Wallet(config=config)
    subtensor = bt.Subtensor(config=config)
    metagraph = subtensor.metagraph(config.netuid)
    dendrite = bt.Dendrite(wallet=wallet)
    make_backend = load_backend(config)

    corpus = json.loads(CORPUS_PATH.read_text()) if CORPUS_PATH.exists() else {}
    scores = np.zeros(len(metagraph.uids), dtype=np.float32)

    while True:
        metagraph.sync(subtensor=subtensor)
        if len(scores) != len(metagraph.uids):
            scores = np.resize(scores, len(metagraph.uids))

        axons = [metagraph.axons[uid] for uid in range(len(metagraph.uids))]
        responses = dendrite.query(axons, CaseSynapse(request_nonce=str(uuid.uuid4())), timeout=30)

        for uid, resp in enumerate(responses):
            case_json = resp if isinstance(resp, str) else getattr(resp, "case_json", None)
            step_score = 0.0
            if case_json:
                try:
                    result = evaluate_case(json.loads(case_json), make_backend(), corpus)
                    step_score = result["score"]
                    bt.logging.info(f"uid={uid} gate={result['gate']} score={step_score}")
                except Exception as e:
                    bt.logging.warning(f"uid={uid} evaluation error: {e}")
            scores[uid] = (1 - EMA_ALPHA) * scores[uid] + EMA_ALPHA * step_score

        CORPUS_PATH.write_text(json.dumps(corpus))

        total = scores.sum()
        if total > 0:
            weights = scores / total
            try:
                subtensor.set_weights(wallet=wallet, netuid=config.netuid,
                                      uids=metagraph.uids, weights=weights,
                                      wait_for_inclusion=False)
                bt.logging.info(f"set_weights ok: {np.round(weights, 3)}")
            except Exception as e:
                bt.logging.warning(f"set_weights failed (rate limit is normal): {e}")
        time.sleep(QUERY_PERIOD_S)

if __name__ == "__main__":
    main()
