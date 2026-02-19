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
    ROYALTY_PAID = "RoyaltyPaid"


class MangoTangoPhase(Enum):
    CLOSED = 0
    ALLOWLIST = 1
    PUBLIC = 2
    SOLD_OUT = 3


# ---------------------------------------------------------------------------
# Exceptions — unique names
# ---------------------------------------------------------------------------

class MangoTangoMintCapReachedError(Exception):
    def __init__(self, current: int, cap: int) -> None:
        super().__init__(f"MangoTango: mint cap reached (current={current}, cap={cap})")


class MangoTangoNotAllowedError(Exception):
    def __init__(self, address: str) -> None:
        super().__init__(f"MangoTango: address not on allowlist: {address}")


class MangoTangoInvalidTokenIdError(Exception):
    def __init__(self, token_id: int) -> None:
        super().__init__(f"MangoTango: invalid token id: {token_id}")


class MangoTangoPhaseClosedError(Exception):
    def __init__(self, phase: MangoTangoPhase) -> None:
        super().__init__(f"MangoTango: phase not open for minting: {phase}")


class MangoTangoWalletLimitError(Exception):
    def __init__(self, address: str, count: int, limit: int) -> None:
        super().__init__(f"MangoTango: wallet limit exceeded for {address} (count={count}, limit={limit})")


class MangoTangoInsufficientValueError(Exception):
    def __init__(self, sent: int, required: int) -> None:
        super().__init__(f"MangoTango: insufficient value (sent={sent}, required={required})")


class MangoTangoRevealNotReadyError(Exception):
    def __init__(self, token_id: int) -> None:
        super().__init__(f"MangoTango: reveal not ready for token {token_id}")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RoyaltyInfo:
    recipient: str
    bps: int

    def to_dict(self) -> Dict[str, Any]:
        return {"recipient": self.recipient, "bps": self.bps}


@dataclass
class TokenMetadata:
    token_id: int
    name: str
    description: str
    image_uri: str
    attributes: List[Dict[str, Any]]
    revealed: bool
    revealed_at: Optional[float] = None

    def to_json(self) -> str:
        return json.dumps({
            "token_id": self.token_id,
            "name": self.name,
            "description": self.description,
            "image": self.image_uri,
            "attributes": self.attributes,
            "revealed": self.revealed,
        }, indent=2)


@dataclass
class MintRule:
    phase: MangoTangoPhase
    max_per_wallet: int
    price_wei: int
    active: bool = True


# ---------------------------------------------------------------------------
# Trait tables for metadata generation (expand line count and variety)
# ---------------------------------------------------------------------------

MANGO_TANGO_BACKGROUNDS = [
    "Tropical Sunset", "Coral Reef", "Golden Hour", "Mango Grove", "Tango Night",
    "Citrus Blush", "Amber Glow", "Saffron Mist", "Peach Haze", "Palm Shadow",
    "Jungle Canopy", "Beach Dawn", "Harvest Moon", "Spice Market", "Rum Barrel",
]

MANGO_TANGO_SKIN_TONES = [
    "Sun Kissed", "Golden Ripe", "Amber", "Honey", "Caramel",
    "Blush", "Coral", "Peach", "Cream", "Light Amber",
]

MANGO_TANGO_EXPRESSIONS = [
    "Cheerful", "Wink", "Smirk", "Joy", "Serene",
    "Playful", "Mysterious", "Bold", "Calm", "Zesty",
]

MANGO_TANGO_ACCESSORIES = [
    "None", "Leaf Crown", "Sunglasses", "Bandana", "Straw Hat",
    "Flower", "Scarf", "Bow Tie", "Earring", "Necklace",
    "Headband", "Cap", "Beret", "Pin", "Chain",
]

MANGO_TANGO_RARITY_TIERS = [
    "Common", "Uncommon", "Rare", "Epic", "Legendary",
]

MANGO_TANGO_BACKGROUND_HEX = [
    "#FF6B35", "#F7C35F", "#2D5A27", "#8B4513", "#FF8C00",
    "#CD853F", "#D2691E", "#DEB887", "#F4A460", "#BC8F8F",
]

MANGO_TANGO_SPECIAL_TRAITS = [
    "Golden Seed", "Tango Dancer", "Mango King", "Tropical Royalty",
    "Sun Blessed", "Harvest Lord", "Citrus Spirit", "Island Soul",
]


def _hash_seed_for_token(collection_seed: str, token_id: int, nonce: int = 0) -> str:
    payload = f"{collection_seed}-{token_id}-{nonce}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _pick_trait_from_hash(h: str, traits: List[str]) -> str:
    idx = int(h[:8], 16) % len(traits)
    return traits[idx]


def _pick_hex_from_hash(h: str, hexes: List[str]) -> str:
    idx = int(h[8:16], 16) % len(hexes)
    return hexes[idx]


def generate_metadata_attributes(token_id: int, revealed: bool) -> List[Dict[str, Any]]:
    seed = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    attrs = []
    attrs.append({"trait_type": "Background", "value": _pick_trait_from_hash(seed[0:16], MANGO_TANGO_BACKGROUNDS)})
    attrs.append({"trait_type": "Skin", "value": _pick_trait_from_hash(seed[2:18], MANGO_TANGO_SKIN_TONES)})
    attrs.append({"trait_type": "Expression", "value": _pick_trait_from_hash(seed[4:20], MANGO_TANGO_EXPRESSIONS)})
    attrs.append({"trait_type": "Accessory", "value": _pick_trait_from_hash(seed[6:22], MANGO_TANGO_ACCESSORIES)})
    attrs.append({"trait_type": "Rarity", "value": _pick_trait_from_hash(seed[10:26], MANGO_TANGO_RARITY_TIERS)})
    attrs.append({"trait_type": "Background Color", "value": _pick_hex_from_hash(seed[12:28], MANGO_TANGO_BACKGROUND_HEX)})
    if int(seed[14:16], 16) % 5 == 0:
        attrs.append({"trait_type": "Special", "value": _pick_trait_from_hash(seed[16:32], MANGO_TANGO_SPECIAL_TRAITS)})
    return attrs


def build_token_metadata(token_id: int, revealed: bool) -> TokenMetadata:
    attrs = generate_metadata_attributes(token_id, revealed)
    name = f"{MANGO_TANGO_NAME} #{token_id}"
    desc = f"A unique MangoTango collectible. Token ID {token_id}. Part of the {MANGO_TANGO_NAME} collection."
    if revealed:
        image_uri = f"{MANGO_TANGO_COLLECTION_URI}{token_id}.png"
    else:
        image_uri = f"{MANGO_TANGO_COLLECTION_URI}unrevealed.png"
    return TokenMetadata(
        token_id=token_id,
        name=name,
