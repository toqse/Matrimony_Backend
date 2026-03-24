import hashlib


RASI_NAMES = [
    'Mesha', 'Vrishabha', 'Mithuna', 'Karka', 'Simha', 'Kanya',
    'Tula', 'Vrischika', 'Dhanus', 'Makara', 'Kumbha', 'Meena',
]

PLANET_NAME_MAP = {
    'sun': 'Su',
    'moon': 'Mo',
    'mars': 'Ma',
    'mercury': 'Me',
    'jupiter': 'Ju',
    'venus': 'Ve',
    'saturn': 'Sa',
    'rahu': 'Ra',
    'ketu': 'Ke',
}


def normalize_degree(value: float) -> float:
    return float(value) % 360.0


def rasi_index_from_longitude(longitude: float) -> int:
    return int(normalize_degree(longitude) // 30)


def rasi_name_from_longitude(longitude: float) -> str:
    return RASI_NAMES[rasi_index_from_longitude(longitude)]


def nakshatra_index_from_longitude(longitude: float) -> int:
    segment = 360.0 / 27.0
    return int(normalize_degree(longitude) // segment)


def nakshatra_pada_from_longitude(longitude: float) -> int:
    segment = 360.0 / 27.0
    pada_span = segment / 4.0
    offset = normalize_degree(longitude) % segment
    return int(offset // pada_span) + 1


def build_birth_input_hash(date_of_birth, time_of_birth, place_of_birth: str) -> str:
    raw = f'{date_of_birth.isoformat()}|{time_of_birth.isoformat()}|{(place_of_birth or "").strip().lower()}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()
