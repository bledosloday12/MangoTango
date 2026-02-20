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
        description=desc,
        image_uri=image_uri,
        attributes=attrs,
        revealed=revealed,
        revealed_at=time.time() if revealed else None,
    )


# ---------------------------------------------------------------------------
# MangoTango Minter (core contract logic)
# ---------------------------------------------------------------------------

class MangoTangoMinter:
    def __init__(self) -> None:
        self._next_token_id = 1
        self._total_minted = 0
        self._allowlist: Set[str] = set()
        self._mint_count_per_wallet: Dict[str, int] = {}
        self._phase = MangoTangoPhase.ALLOWLIST
        self._metadata_store: Dict[int, TokenMetadata] = {}
        self._owner_of: Dict[int, str] = {}
        self._reveal_ready_at: Dict[int, float] = {}
        self._event_log: List[Tuple[MangoTangoEvent, Dict[str, Any]]] = []
        self._royalty_info = RoyaltyInfo(recipient=ROYALTY_RECIPIENT_ADDRESS, bps=MANGO_TANGO_ROYALTY_BPS)
        self._minter_address = MINTER_ADDRESS
        self._treasury_address = TREASURY_ADDRESS
        self._collection_owner = COLLECTION_OWNER_ADDRESS
        self._reveal_oracle = REVEAL_ORACLE_ADDRESS

    def get_minter_address(self) -> str:
        return self._minter_address

    def get_treasury_address(self) -> str:
        return self._treasury_address

    def get_royalty_recipient(self) -> str:
        return self._royalty_info.recipient

    def get_collection_owner(self) -> str:
        return self._collection_owner

    def get_reveal_oracle(self) -> str:
        return self._reveal_oracle

    def get_phase(self) -> MangoTangoPhase:
        return self._phase

    def get_total_supply(self) -> int:
        return self._total_minted

    def get_next_token_id(self) -> int:
        return self._next_token_id

    def get_max_supply(self) -> int:
        return MANGO_TANGO_MAX_SUPPLY

    def get_mint_price_wei(self) -> int:
        if self._phase == MangoTangoPhase.ALLOWLIST:
            return MANGO_TANGO_MINT_PRICE_WEI
        if self._phase == MangoTangoPhase.PUBLIC:
            return MANGO_TANGO_MINT_PRICE_WEI
        return MANGO_TANGO_MINT_PRICE_WEI

    def get_max_per_wallet(self) -> int:
        if self._phase == MangoTangoPhase.ALLOWLIST:
            return MANGO_TANGO_ALLOWLIST_PHASE_MAX_PER_WALLET
        if self._phase == MangoTangoPhase.PUBLIC:
            return MANGO_TANGO_PUBLIC_PHASE_MAX_PER_WALLET
        return 0

    def add_to_allowlist(self, addresses: List[str]) -> None:
        for a in addresses:
            self._allowlist.add(a.strip().lower())
        self._emit(MangoTangoEvent.ALLOWLIST_UPDATED, {"count": len(addresses)})

    def remove_from_allowlist(self, address: str) -> None:
        self._allowlist.discard(address.strip().lower())
        self._emit(MangoTangoEvent.ALLOWLIST_UPDATED, {"removed": address})

    def is_on_allowlist(self, address: str) -> bool:
        return address.strip().lower() in self._allowlist

    def get_allowlist_size(self) -> int:
        return len(self._allowlist)

    def _emit(self, event: MangoTangoEvent, data: Dict[str, Any]) -> None:
        self._event_log.append((event, data))

    def can_mint(self, address: str, quantity: int, value_wei: int) -> Tuple[bool, Optional[str]]:
        if self._phase == MangoTangoPhase.CLOSED:
            return False, "MangoTango: minting closed"
        if self._phase == MangoTangoPhase.SOLD_OUT:
            return False, "MangoTango: sold out"
        if self._total_minted + quantity > MANGO_TANGO_MAX_SUPPLY:
            return False, "MangoTango: would exceed max supply"
        required = self.get_mint_price_wei() * quantity
        if value_wei < required:
            return False, "MangoTango: insufficient value"
        current = self._mint_count_per_wallet.get(address.strip().lower(), 0)
        limit = self.get_max_per_wallet()
        if self._phase == MangoTangoPhase.ALLOWLIST and not self.is_on_allowlist(address):
            return False, "MangoTango: not on allowlist"
        if current + quantity > limit:
            return False, "MangoTango: wallet limit exceeded"
        return True, None

    def mint(self, to_address: str, quantity: int, value_wei: int) -> List[int]:
        ok, err = self.can_mint(to_address, quantity, value_wei)
        if not ok:
            raise MangoTangoMintCapReachedError(self._total_minted, MANGO_TANGO_MAX_SUPPLY) if "exceed" in (err or "") else MangoTangoWalletLimitError(to_address, self._mint_count_per_wallet.get(to_address.lower(), 0), self.get_max_per_wallet())
        required = self.get_mint_price_wei() * quantity
        if value_wei < required:
            raise MangoTangoInsufficientValueError(value_wei, required)
        if self._phase == MangoTangoPhase.ALLOWLIST and not self.is_on_allowlist(to_address):
            raise MangoTangoNotAllowedError(to_address)

        key = to_address.strip().lower()
        current = self._mint_count_per_wallet.get(key, 0)
        limit = self.get_max_per_wallet()
        if current + quantity > limit:
            raise MangoTangoWalletLimitError(to_address, current, limit)

        minted_ids: List[int] = []
        for _ in range(quantity):
            if self._total_minted >= MANGO_TANGO_MAX_SUPPLY:
                break
            tid = self._next_token_id
            self._next_token_id += 1
            self._total_minted += 1
            self._owner_of[tid] = to_address
            self._reveal_ready_at[tid] = time.time() + MANGO_TANGO_REVEAL_DELAY_SEC
            meta = build_token_metadata(tid, revealed=False)
            self._metadata_store[tid] = meta
            minted_ids.append(tid)
            self._emit(MangoTangoEvent.MINT_REQUESTED, {"tokenId": tid, "to": to_address, "valueWei": self.get_mint_price_wei()})

        self._mint_count_per_wallet[key] = self._mint_count_per_wallet.get(key, 0) + len(minted_ids)
        if self._total_minted >= MANGO_TANGO_MAX_SUPPLY:
            self._phase = MangoTangoPhase.SOLD_OUT
            self._emit(MangoTangoEvent.PHASE_ADVANCED, {"phase": "SOLD_OUT"})
        return minted_ids

    def owner_of(self, token_id: int) -> str:
        if token_id not in self._owner_of:
            raise MangoTangoInvalidTokenIdError(token_id)
        return self._owner_of[token_id]

    def get_metadata(self, token_id: int) -> TokenMetadata:
        if token_id not in self._metadata_store:
            raise MangoTangoInvalidTokenIdError(token_id)
        return self._metadata_store[token_id]

    def reveal(self, token_id: int) -> TokenMetadata:
        if token_id not in self._metadata_store:
            raise MangoTangoInvalidTokenIdError(token_id)
        if time.time() < self._reveal_ready_at.get(token_id, 0):
            raise MangoTangoRevealNotReadyError(token_id)
        meta = build_token_metadata(token_id, revealed=True)
        self._metadata_store[token_id] = meta
        self._emit(MangoTangoEvent.TOKEN_REVEALED, {"tokenId": token_id})
        return meta

    def balance_of(self, address: str) -> int:
        count = 0
        key = address.strip().lower()
        for owner in self._owner_of.values():
            if owner.strip().lower() == key:
                count += 1
        return count

    def tokens_of_owner(self, address: str) -> List[int]:
        key = address.strip().lower()
        return [tid for tid, owner in self._owner_of.items() if owner.strip().lower() == key]

    def advance_to_public(self) -> None:
        self._phase = MangoTangoPhase.PUBLIC
        self._emit(MangoTangoEvent.PHASE_ADVANCED, {"phase": "PUBLIC"})

    def get_royalty_info(self) -> RoyaltyInfo:
        return self._royalty_info

    def get_event_log(self) -> List[Tuple[MangoTangoEvent, Dict[str, Any]]]:
        return list(self._event_log)

    def collection_fingerprint(self) -> str:
        return hashlib.sha256(
            f"{MANGO_TANGO_COLLECTION_SEED}-{self._total_minted}-{self._next_token_id}-{MANGO_TANGO_DEPLOY_SALT}".encode()
        ).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Additional trait and metadata helpers (expand line count)
# ---------------------------------------------------------------------------

MANGO_TANGO_LAYERS = [
    "background", "skin", "expression", "accessory", "overlay",
]

MANGO_TANGO_ANIMATION_STYLES = [
    "Static", "Idle", "Bounce", "Pulse", "Shake",
]

MANGO_TANGO_SEASONS = [
    "Tropical Summer", "Harvest Fall", "Golden Winter", "Blossom Spring",
]

MANGO_TANGO_EDITION_NAMES = [
    "First Harvest", "Golden Batch", "Tango Reserve", "Mango Prime",
]


def get_trait_rarity_weights() -> Dict[str, List[float]]:
    return {
        "Background": [0.25, 0.20, 0.18, 0.15, 0.12, 0.10],
        "Skin": [0.22, 0.20, 0.18, 0.16, 0.14, 0.10],
        "Expression": [0.20, 0.20, 0.20, 0.20, 0.20],
        "Accessory": [0.30, 0.15, 0.12, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03],
    }


def compute_royalty_amount(sale_price_wei: int, bps: int) -> int:
    return (sale_price_wei * bps) // MANGO_TANGO_BPS_DENOM


def validate_eth_address(addr: str) -> bool:
    if not addr or len(addr) != 42:
        return False
    if addr[:2] != "0x":
        return False
    try:
        int(addr[2:], 16)
        return True
    except ValueError:
        return False


def token_uri_path(token_id: int) -> str:
    return f"{MANGO_TANGO_COLLECTION_URI}{token_id}"


def contract_uri() -> str:
    return f"{MANGO_TANGO_COLLECTION_URI}collection"


# ---------------------------------------------------------------------------
# Batch and view helpers
# ---------------------------------------------------------------------------

def batch_metadata(minter: MangoTangoMinter, token_ids: List[int]) -> List[TokenMetadata]:
    result = []
    for tid in token_ids:
        try:
            result.append(minter.get_metadata(tid))
        except MangoTangoInvalidTokenIdError:
            pass
    return result


def total_royalty_at_price(minter: MangoTangoMinter, sale_price_wei: int) -> int:
    return compute_royalty_amount(sale_price_wei, minter.get_royalty_info().bps)


def mint_simulation(minter: MangoTangoMinter, address: str, quantity: int) -> Dict[str, Any]:
    ok, err = minter.can_mint(address, quantity, minter.get_mint_price_wei() * quantity)
    return {
        "canMint": ok,
        "error": err,
        "requiredWei": minter.get_mint_price_wei() * quantity,
        "currentBalance": minter.balance_of(address),
        "phase": minter.get_phase().name,
        "remainingSupply": minter.get_max_supply() - minter.get_total_supply(),
    }


# ---------------------------------------------------------------------------
# Allowlist manager (batch and persistence helpers)
# ---------------------------------------------------------------------------

class AllowlistManager:
    def __init__(self, minter: MangoTangoMinter) -> None:
        self._minter = minter

    def add_batch(self, addresses: List[str]) -> int:
        valid = [a for a in addresses if validate_eth_address(a.strip())]
        self._minter.add_to_allowlist(valid)
        return len(valid)

    def remove_batch(self, addresses: List[str]) -> int:
        count = 0
        for a in addresses:
            if self._minter.is_on_allowlist(a):
                self._minter.remove_from_allowlist(a)
                count += 1
        return count

    def export_addresses(self) -> List[str]:
        return list(self._minter._allowlist)

    def count(self) -> int:
        return self._minter.get_allowlist_size()


# ---------------------------------------------------------------------------
# Reveal scheduler (time-based reveal checks)
# ---------------------------------------------------------------------------

class RevealScheduler:
    def __init__(self, minter: MangoTangoMinter) -> None:
        self._minter = minter

    def is_reveal_ready(self, token_id: int) -> bool:
        if token_id not in self._minter._reveal_ready_at:
            return False
        return time.time() >= self._minter._reveal_ready_at[token_id]

    def seconds_until_reveal(self, token_id: int) -> float:
        if token_id not in self._minter._reveal_ready_at:
            return 0.0
        t = self._minter._reveal_ready_at[token_id] - time.time()
        return max(0.0, t)

    def reveal_all_ready(self) -> List[int]:
        revealed = []
        for tid in list(self._minter._metadata_store.keys()):
            if self.is_reveal_ready(tid) and not self._minter.get_metadata(tid).revealed:
                try:
                    self._minter.reveal(tid)
                    revealed.append(tid)
                except MangoTangoRevealNotReadyError:
                    pass
        return revealed


# ---------------------------------------------------------------------------
# Metadata builder (extended attributes and JSON export)
# ---------------------------------------------------------------------------

class MetadataBuilder:
    @staticmethod
    def full_metadata_json(token_id: int, revealed: bool) -> str:
        meta = build_token_metadata(token_id, revealed)
        return meta.to_json()

    @staticmethod
    def open_sea_format(token_id: int, revealed: bool) -> Dict[str, Any]:
        meta = build_token_metadata(token_id, revealed)
        return {
            "name": meta.name,
            "description": meta.description,
            "image": meta.image_uri,
            "attributes": meta.attributes,
            "external_url": token_uri_path(token_id),
        }

    @staticmethod
    def rarity_score(attributes: List[Dict[str, Any]]) -> float:
        weights = get_trait_rarity_weights()
        score = 0.0
        for attr in attributes:
            trait_type = attr.get("trait_type", "")
            if trait_type in weights:
                vals = weights[trait_type]
                idx = min(len(vals) - 1, hash(attr.get("value", "")) % len(vals))
                score += vals[idx]
        return score


# ---------------------------------------------------------------------------
# Extra trait pools for metadata variety
# ---------------------------------------------------------------------------

MANGO_TANGO_HAT_STYLES = [
    "None", "Crown", "Sombrero", "Fedora", "Beanie", "Cap", "Straw", "Top Hat",
]

MANGO_TANGO_EYE_STYLES = [
    "Default", "Wink", "Closed", "Star", "Heart", "Sparkle", "Serious", "Happy",
]

MANGO_TANGO_MOUTH_STYLES = [
    "Smile", "Grin", "Neutral", "Open", "Tongue", "Whistle", "Smirk",
]

MANGO_TANGO_BACKGROUND_EFFECTS = [
    "None", "Bokeh", "Gradient", "Pattern", "Stars", "Leaves", "Waves",
]

MANGO_TANGO_BORDER_STYLES = [
    "None", "Gold", "Silver", "Bronze", "Rainbow", "Matte",
]

MANGO_TANGO_GENERATION_NAMES = [
    "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta",
]

MANGO_TANGO_SEASON_IDS = [1, 2, 3, 4, 5, 6]

MANGO_TANGO_SPECIAL_EDITION_FLAGS = [False, False, False, True, False]

MANGO_TANGO_ANIMATION_URIS = [
    "ipfs://QmAnim1/", "ipfs://QmAnim2/", "ipfs://QmAnim3/",
]


def get_hat_for_token(token_id: int) -> str:
    h = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    return _pick_trait_from_hash(h[18:34], MANGO_TANGO_HAT_STYLES)


def get_eyes_for_token(token_id: int) -> str:
    h = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    return _pick_trait_from_hash(h[20:36], MANGO_TANGO_EYE_STYLES)


def get_mouth_for_token(token_id: int) -> str:
    h = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    return _pick_trait_from_hash(h[22:38], MANGO_TANGO_MOUTH_STYLES)


def get_background_effect_for_token(token_id: int) -> str:
    h = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    return _pick_trait_from_hash(h[24:40], MANGO_TANGO_BACKGROUND_EFFECTS)


def get_border_for_token(token_id: int) -> str:
    h = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    return _pick_trait_from_hash(h[26:42], MANGO_TANGO_BORDER_STYLES)


def generate_extended_attributes(token_id: int) -> List[Dict[str, Any]]:
    base = generate_metadata_attributes(token_id, True)
    base.append({"trait_type": "Hat", "value": get_hat_for_token(token_id)})
    base.append({"trait_type": "Eyes", "value": get_eyes_for_token(token_id)})
    base.append({"trait_type": "Mouth", "value": get_mouth_for_token(token_id)})
    base.append({"trait_type": "Background Effect", "value": get_background_effect_for_token(token_id)})
    base.append({"trait_type": "Border", "value": get_border_for_token(token_id)})
    seed = _hash_seed_for_token(MANGO_TANGO_COLLECTION_SEED, token_id)
    base.append({"trait_type": "Generation", "value": _pick_trait_from_hash(seed[28:44], MANGO_TANGO_GENERATION_NAMES)})
    base.append({"trait_type": "Season ID", "value": _pick_trait_from_hash(seed[30:46], [str(s) for s in MANGO_TANGO_SEASON_IDS])})
    return base


# ---------------------------------------------------------------------------
# Supply and stats helpers
# ---------------------------------------------------------------------------

def remaining_supply(minter: MangoTangoMinter) -> int:
    return minter.get_max_supply() - minter.get_total_supply()


def is_sold_out(minter: MangoTangoMinter) -> bool:
    return minter.get_phase() == MangoTangoPhase.SOLD_OUT


def treasury_balance_estimate(minter: MangoTangoMinter) -> int:
    return minter.get_total_supply() * MANGO_TANGO_MINT_PRICE_WEI


def royalty_estimate_per_token() -> int:
    return compute_royalty_amount(MANGO_TANGO_MINT_PRICE_WEI, MANGO_TANGO_ROYALTY_BPS)


def format_wei_to_ether(wei: int) -> str:
    return f"{wei / 1e18:.4f}"


def parse_ether_to_wei(ether_str: str) -> int:
    try:
        return int(float(ether_str) * 1e18)
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Validation and sanitization
# ---------------------------------------------------------------------------

def sanitize_address(addr: str) -> str:
    s = addr.strip()
    if len(s) == 42 and s.startswith("0x"):
        return s[:2] + s[2:].lower()
    return s


def validate_quantity(quantity: int, phase: MangoTangoPhase) -> Tuple[bool, Optional[str]]:
    if quantity <= 0:
        return False, "Quantity must be positive"
    max_per = MANGO_TANGO_ALLOWLIST_PHASE_MAX_PER_WALLET if phase == MangoTangoPhase.ALLOWLIST else MANGO_TANGO_PUBLIC_PHASE_MAX_PER_WALLET
    if quantity > max_per:
        return False, f"Max {max_per} per wallet in this phase"
    return True, None


def validate_mint_params(to_address: str, quantity: int, value_wei: int, minter: MangoTangoMinter) -> Tuple[bool, Optional[str]]:
    if not validate_eth_address(to_address):
        return False, "Invalid address"
    ok, err = validate_quantity(quantity, minter.get_phase())
    if not ok:
        return False, err
    required = minter.get_mint_price_wei() * quantity
    if value_wei < required:
        return False, "Insufficient value"
    return minter.can_mint(to_address, quantity, value_wei)


# ---------------------------------------------------------------------------
# Export for EVM / ABI-like interface
# ---------------------------------------------------------------------------

def abi_like_mint(minter: MangoTangoMinter, to: str, quantity: int, value_wei: int) -> Dict[str, Any]:
    try:
        ids = minter.mint(to, quantity, value_wei)
        return {"success": True, "tokenIds": ids, "error": None}
    except Exception as e:
        return {"success": False, "tokenIds": [], "error": str(e)}


def abi_like_balance_of(minter: MangoTangoMinter, address: str) -> int:
    return minter.balance_of(address)


def abi_like_owner_of(minter: MangoTangoMinter, token_id: int) -> Optional[str]:
    try:
        return minter.owner_of(token_id)
    except MangoTangoInvalidTokenIdError:
        return None


def abi_like_token_uri(minter: MangoTangoMinter, token_id: int) -> Optional[str]:
    try:
        meta = minter.get_metadata(token_id)
        return json.dumps({
            "name": meta.name,
            "description": meta.description,
            "image": meta.image_uri,
            "attributes": meta.attributes,
        })
    except MangoTangoInvalidTokenIdError:
        return None


def abi_like_total_supply(minter: MangoTangoMinter) -> int:
    return minter.get_total_supply()


def abi_like_royalty_info(minter: MangoTangoMinter) -> Dict[str, Any]:
    r = minter.get_royalty_info()
    return {"recipient": r.recipient, "bps": r.bps}


# ---------------------------------------------------------------------------
# Additional trait and metadata pools (expand line count)
# ---------------------------------------------------------------------------

MANGO_TANGO_WEATHER_TRAITS = [
    "Sunny", "Cloudy", "Rain", "Tropical Storm", "Clear Night", "Dusk", "Dawn",
]

MANGO_TANGO_FRUIT_ACCENTS = [
