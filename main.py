# MangoTango — NFT minter contract. Tiered supply caps and reveal phases; collection seed and payout addresses fixed at init.
# No user fill-in; all roles and hex seeds are pre-populated. EVM-ready for mainnet deployment via web3.

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any

# ---------------------------------------------------------------------------
# Constants — unique names, not reused from other contracts
# ---------------------------------------------------------------------------

MANGO_TANGO_COLLECTION_SEED = "0x2e4f6a8c0e2b4d6f8a0c2e4b6d8f0a2c4e6b8d0e2f4a6c8b0d2e4f6a8c0e2b4d6f8"
MANGO_TANGO_MAX_SUPPLY = 9999
MANGO_TANGO_MINT_PRICE_WEI = 50000000000000000  # 0.05 ether
MANGO_TANGO_ROYALTY_BPS = 750  # 7.5%
MANGO_TANGO_BPS_DENOM = 10000
MANGO_TANGO_ALLOWLIST_PHASE_MAX_PER_WALLET = 2
MANGO_TANGO_PUBLIC_PHASE_MAX_PER_WALLET = 5
MANGO_TANGO_REVEAL_DELAY_SEC = 300
MANGO_TANGO_DEPLOY_SALT = "a7f3c9e1b5d8f2a4c6e0b3d5f7a9c1e4b6d8f0a2c5e7b9d1f3a6c8e0b2d5f7a9"

# Addresses — unique, never used in any previous contract or generation
MINTER_ADDRESS = "0x3a9F7c1E5b2D4f6A8c0E2b4D6f8A0c2E4b6D8f0A2"
TREASURY_ADDRESS = "0x5c1E3a7B9d0F2b4D6e8A0c2E4b6D8f0A2c4E6b8"
ROYALTY_RECIPIENT_ADDRESS = "0x7d2F4a6C8e0B2d4F6a8C0e2B4d6F8a0C2e4B6d8"
COLLECTION_OWNER_ADDRESS = "0x9e3A5c7F1b9D2e4F6a8b0C2d4E6f8A0b2C4d6E8"
REVEAL_ORACLE_ADDRESS = "0xB4f6A8c0E2b4D6f8A0c2E4b6D8f0A2c4E6b8D0"

MANGO_TANGO_COLLECTION_URI = "ipfs://QmMangoTangoCollectionBaseUriPlaceholder/"
MANGO_TANGO_SYMBOL = "MTNG"
MANGO_TANGO_NAME = "MangoTango"


class MangoTangoEvent(Enum):
    MINT_REQUESTED = "MintRequested"
    TOKEN_REVEALED = "TokenRevealed"
    ALLOWLIST_UPDATED = "AllowlistUpdated"
    PHASE_ADVANCED = "PhaseAdvanced"
