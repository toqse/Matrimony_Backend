"""
Malayalam / Kerala-style labels for South Indian Rasi (Grahanila) chart.
Planet glyphs follow common Malayalam jathakam abbreviations (രവി, ചന്ദ്രൻ, …).
"""
# Rasi (whole-sign house) -> grid cell (col 0-3, row 0-3), top-left origin.
# Perimeter matches classic South Indian fixed-rasi layout (Meena top-left, clockwise).
RASI_TO_GRID = {
    'Meena': (0, 0),
    'Mesha': (1, 0),
    'Vrishabha': (2, 0),
    'Mithuna': (3, 0),
    'Karka': (3, 1),
    'Simha': (3, 2),
    'Kanya': (3, 3),
    'Tula': (2, 3),
    'Vrischika': (1, 3),
    'Dhanus': (0, 3),
    'Makara': (0, 2),
    'Kumbha': (0, 1),
}

# Small rasi name label inside each box (Malayalam)
RASI_LABEL_MLY = {
    'Meena': 'മീനം',
    'Mesha': 'മേടം',
    'Vrishabha': 'ഇടവം',
    'Mithuna': 'മിഥുനം',
    'Karka': 'കർക്കടകം',
    'Simha': 'ചിങ്ങം',
    'Kanya': 'കന്നി',
    'Tula': 'തുലാം',
    'Vrischika': 'വൃശ്ചികം',
    'Dhanus': 'ധനു',
    'Makara': 'മകരം',
    'Kumbha': 'കുംഭം',
}

# Graha keys match grahanila JSON planet keys
PLANET_MLY = {
    'sun': 'ര',
    'moon': 'ച',
    'mars': 'കു',
    'mercury': 'ബു',
    'jupiter': 'ഗു',
    'venus': 'ശു',
    'saturn': 'ശനി',
    'rahu': 'റാ',
    'ketu': 'കേ',
}

LAGNA_MLY = 'ലഗ്നം'
TITLE_MLY = 'ഗ്രഹനില'

GENDER_MLY = {
    'M': 'പുരുഷൻ',
    'F': 'സ്ത്രീ',
    'O': '',
}

# English nakshatra name (as stored in Horoscope) -> Malayalam (Kerala star names)
NAKSHATRA_MALAYALAM = {
    'Ashwini': 'അശ്വതി',
    'Bharani': 'ഭരണി',
    'Krittika': 'കാർത്തിക',
    'Rohini': 'രോഹിണി',
    'Mrigashirsha': 'മകയിരം',
    'Ardra': 'തിരുവാതിര',
    'Punarvasu': 'പുണർതം',
    'Pushya': 'പൂയം',
    'Ashlesha': 'ആയില്യം',
    'Magha': 'മകം',
    'Purva Phalguni': 'പൂരം',
    'Uttara Phalguni': 'ഉത്രം',
    'Hasta': 'അത്തം',
    'Chitra': 'ചിത്ര',
    'Swati': 'ചോതി',
    'Vishakha': 'വിശാഖം',
    'Anuradha': 'അനിഴം',
    'Jyeshtha': 'തൃക്കേട്ട',
    'Mula': 'മൂലം',
    'Purva Ashadha': 'പൂരാടം',
    'Uttara Ashadha': 'ഉത്രാടം',
    'Shravana': 'തിരുവോണം',
    'Dhanishta': 'അവിട്ടം',
    'Shatabhisha': 'ചതയം',
    'Purva Bhadrapada': 'പൂരുരുട്ടാതി',
    'Uttara Bhadrapada': 'ഉത്രട്ടാതി',
    'Revati': 'രേവതി',
}
