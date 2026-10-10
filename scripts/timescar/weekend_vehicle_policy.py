"""Owner-authorized vehicle order for the weekend recurring booking pair."""
import re
import unicodedata

PREFERRED_CAR_ID = '1244976'


def normalized(text: str) -> str:
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


def vehicle_rank(label: str) -> int | None:
    name = normalized(label)
    name = re.sub(r'^(?:ベーシック|ミドル|プレミアム)/', '', name)
    if name.startswith('ヤリスクロス(ハイブリッド)'):
        return 0
    if name.startswith('ライズ(ハイブリッド)'):
        return 1
    if re.match(r'^ソリオ(?:\(|$)', name):
        return 2
    return None


def ordered_candidates(options: list[dict]) -> list[dict]:
    candidates = []
    seen = set()
    for option in options:
        rank = vehicle_rank(option['text'])
        value = option['value']
        if rank is None or not value or value in seen:
            continue
        if rank == 0 and value != PREFERRED_CAR_ID:
            continue
        candidates.append(option)
        seen.add(value)
    return sorted(candidates, key=lambda option: vehicle_rank(option['text']))


def allowed_reservation(reservation: dict) -> bool:
    name = normalized(str(reservation.get('vehicle') or ''))
    if name in ('ヤリスクロス', 'ソリオ'):
        return True
    if vehicle_rank(name) is not None:
        return True
    return name == 'ライズ' and 'ハイブリッド' in normalized(str(reservation.get('carIdentifier') or ''))
