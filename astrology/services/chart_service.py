from io import BytesIO

from PIL import Image, ImageDraw

from .utils import rasi_name_from_longitude


CELL_MAP_SOUTH = {
    1: (0, 0), 2: (1, 0), 3: (2, 0), 4: (3, 0),
    5: (3, 1), 6: (3, 2), 7: (3, 3), 8: (2, 3),
    9: (1, 3), 10: (0, 3), 11: (0, 2), 12: (0, 1),
}


def _build_house_planet_map(grahanila: dict):
    houses = {idx: [] for idx in range(1, 13)}
    planets = (grahanila or {}).get('planets', {})
    for name, info in planets.items():
        longitude = info.get('longitude')
        if longitude is None:
            continue
        rasi = rasi_name_from_longitude(longitude)
        house = _rasi_to_house_index(rasi)
        short_name = info.get('short_name', name[:2].title())
        houses[house].append(short_name)
    return houses


def _rasi_to_house_index(rasi_name: str) -> int:
    all_rasis = [
        'Mesha', 'Vrishabha', 'Mithuna', 'Karka', 'Simha', 'Kanya',
        'Tula', 'Vrischika', 'Dhanus', 'Makara', 'Kumbha', 'Meena',
    ]
    return all_rasis.index(rasi_name) + 1 if rasi_name in all_rasis else 1


def generate_chart_image(grahanila: dict, style: str = 'south') -> bytes:
    if style not in ('south', 'north'):
        style = 'south'

    image = Image.new('RGB', (900, 900), color='white')
    draw = ImageDraw.Draw(image)
    step = 225

    for i in range(5):
        draw.line((0, i * step, 900, i * step), fill='black', width=2)
        draw.line((i * step, 0, i * step, 900), fill='black', width=2)

    houses = _build_house_planet_map(grahanila)
    mapping = CELL_MAP_SOUTH
    for house, planets in houses.items():
        x_idx, y_idx = mapping[house]
        x = x_idx * step + 10
        y = y_idx * step + 10
        draw.text((x, y), f'H{house}: {", ".join(planets) if planets else "-"}', fill='black')

    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
