"""Wire protocol: validator queries miners; miner responds with one case (JSON string)."""
from typing import Optional
import bittensor as bt

class CaseSynapse(bt.Synapse):
    # filled by validator (request context)
    request_nonce: str = ""
    # filled by miner (response)
    case_json: Optional[str] = None

    def deserialize(self) -> Optional[str]:
        return self.case_json
