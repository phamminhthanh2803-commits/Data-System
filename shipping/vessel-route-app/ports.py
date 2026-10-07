"""Catalog of representative ports per ocean region, BY VESSEL TYPE.

Different vessels call at different terminals:
  - crude:     VLCC/Aframax → crude-oil terminals (Ras Tanura, Houston, Bonny…)
  - chemical:  product/chemical tankers → chemical hubs (Antwerp, Map Ta Phut, Houston…)
  - gas:       LNG/LPG carriers → liquefaction/regas terminals (Ras Laffan, Sabine Pass, Gladstone…)
  - container: container ships → mega-hubs (Shanghai, Singapore, Rotterdam, LA/LB…)
  - general:   fallback (uses crude mapping by default)

PORTS holds (lon, lat) for every port name referenced below.
Use resolve_port(region, vessel_type='crude') from app.py.
"""
from __future__ import annotations

# ---------- master coordinate catalog ----------

PORTS = {
    # SE Asia / East Asia
    "Singapore":          (103.80,   1.26),
    "Port Klang":         (101.36,   3.00),
    "Tanjung Pelepas":    (103.55,   1.36),
    "Map Ta Phut":        (101.16,  12.69),
    "Laem Chabang":       (100.88,  13.08),
    "Pasir Gudang":       (103.90,   1.45),
    "Ho Chi Minh City":   (106.80,  10.77),
    "Cai Mep":            (107.03,  10.53),
    "Manila":             (120.97,  14.59),
    "Jakarta (Tanjung Priok)": (106.88, -6.11),
    "Cilacap":            (109.00,  -7.73),
    "Bontang LNG":        (117.48,   0.13),
    "Tangguh LNG":        (133.10,  -2.40),
    "Balikpapan":         (116.83,  -1.27),
    "Makassar":           (119.40,  -5.13),
    "Bitung":             (125.18,   1.45),
    "Ternate":            (127.38,   0.78),
    "Ningbo-Zhoushan":    (122.07,  29.95),
    "Shanghai":           (122.06,  30.62),
    "Yangshan":           (122.08,  30.62),
    "Shenzhen (Yantian)": (114.27,  22.57),
    "Qingdao":            (120.32,  36.07),
    "Dalian":             (121.65,  38.92),
    "Tianjin":            (117.78,  38.97),
    "Tianjin LNG":        (117.85,  38.78),
    "Hong Kong":          (114.16,  22.30),
    "Kaohsiung":          (120.30,  22.62),
    "Yokohama":           (139.70,  35.45),
    "Chiba":              (140.10,  35.58),
    "Yokkaichi":          (136.65,  34.97),
    "Sodegaura LNG":      (140.00,  35.43),
    "Futtsu LNG":         (139.78,  35.32),
    "Senboku LNG":        (135.42,  34.55),
    "Ulsan":              (129.40,  35.50),
    "Busan":              (129.07,  35.10),
    "Yeosu":              (127.78,  34.75),
    "Incheon LNG":        (126.50,  37.42),
    "Vladivostok":        (131.88,  43.10),
    # South Asia
    "Mumbai (JNPT)":      ( 72.95,  18.95),
    "Mundra":             ( 69.72,  22.75),
    "Sikka":              ( 69.85,  22.43),
    "Vizag":              ( 83.30,  17.69),
    "Chennai":            ( 80.30,  13.10),
    "Chittagong":         ( 91.83,  22.30),
    "Colombo":            ( 79.85,   6.95),
    "Hambantota":         ( 81.12,   6.13),
    # Middle East
    "Ras Tanura":         ( 50.16,  26.71),
    "Fujairah":           ( 56.36,  25.17),
    "Jebel Ali":          ( 55.05,  25.02),
    "Khor Fakkan":        ( 56.36,  25.34),
    "Sohar":              ( 56.62,  24.50),
    "Kharg Island":       ( 50.32,  29.25),
    "Basra":              ( 47.80,  30.50),
    "Mina Al Ahmadi":     ( 48.15,  29.07),
    "Ras Laffan LNG":     ( 51.59,  25.92),
    "Yanbu":              ( 38.06,  24.10),
    "Jubail":             ( 49.65,  27.02),
    "Mesaieed":           ( 51.55,  24.97),
    # Africa
    "Bonny":              (  7.30,   4.42),
    "Escravos":           (  5.18,   5.55),
    "Mombasa":            ( 39.65,  -4.04),
    "Durban":             ( 31.04, -29.87),
    "Cape Town":          ( 18.43, -33.90),
    "Lagos":              (  3.40,   6.43),
    "Tanger Med":         ( -5.50,  35.88),
    "Sidi Kerir":         ( 29.65,  31.10),
    "Suez (Red Sea side)":( 32.55,  29.93),
    "Port Said":          ( 32.30,  31.25),
    # Europe
    "Rotterdam":          (   4.13,  51.95),
    "Antwerp":            (   4.30,  51.30),
    "Hamburg":            (   9.97,  53.55),
    "Le Havre":           (   0.10,  49.48),
    "Bremerhaven":        (   8.55,  53.55),
    "Algeciras":          (  -5.43,  36.13),
    "Valencia":           (  -0.33,  39.45),
    "Tarragona":          (   1.22,  41.10),
    "Piraeus":            (  23.62,  37.94),
    "Augusta":            (  15.22,  37.20),
    "Ceyhan":             (  35.83,  36.85),
    "Istanbul":           (  29.10,  41.00),
    "Novorossiysk":       (  37.78,  44.72),
    "Zeebrugge LNG":      (   3.18,  51.35),
    "Sines":              (  -8.83,  37.95),
    "Bilbao":             (  -3.05,  43.36),
    # Americas — West / Pacific
    "Long Beach":         (-118.21,  33.75),
    "Los Angeles":        (-118.27,  33.72),
    "Oakland":            (-122.30,  37.80),
    "Seattle":            (-122.34,  47.60),
    "Tacoma":             (-122.42,  47.27),
    "Vancouver BC":       (-123.12,  49.29),
    "Valdez":             (-146.35,  61.13),
    "Panama (Pacific)":   ( -79.55,   8.88),
    "Manzanillo MX":      (-104.32,  19.05),
    "Lazaro Cardenas":    (-102.18,  17.95),
    "Callao":             ( -77.15, -12.05),
    "Valparaiso":         ( -71.62, -33.04),
    # Americas — East / Gulf
    "Houston":            ( -95.06,  29.34),
    "Corpus Christi":     ( -97.40,  27.81),
    "New Orleans":        ( -90.07,  29.95),
    "Sabine Pass LNG":    ( -93.88,  29.73),
    "Freeport LNG":       ( -95.31,  28.95),
    "Cameron LNG":        ( -93.33,  29.79),
    "LOOP":               ( -90.03,  28.88),
    "Pascagoula":         ( -88.50,  30.35),
    "New York / NJ":      ( -74.05,  40.66),
    "Savannah":           ( -81.13,  32.13),
    "Charleston":         ( -79.93,  32.78),
    "Norfolk":            ( -76.30,  36.92),
    "Cove Point LNG":     ( -76.39,  38.40),
    "Santos":             ( -46.32, -23.97),
    "Tubarao":            ( -40.25, -20.28),
    "Buenos Aires":       ( -58.37, -34.60),
    "Cartagena CO":       ( -75.55,  10.40),
    "Panama (Atlantic)":  ( -79.92,   9.36),
    "Kingston":           ( -76.78,  17.97),
    # Australia / Pacific
    "Gladstone":          ( 151.25, -23.84),
    "Gladstone LNG":      ( 151.18, -23.78),
    "Port Hedland":       ( 118.57, -20.31),
    "Dampier":            ( 116.71, -20.66),
    "Karratha LNG":       ( 116.78, -20.59),
    "Newcastle AU":       ( 151.78, -32.92),
    "Sydney":             ( 151.20, -33.84),
    "Brisbane":           ( 153.17, -27.38),
    "Melbourne":          ( 144.93, -37.83),
    "Tauranga":           ( 176.18, -37.65),
    "Honolulu":           (-157.87,  21.31),
}


# ---------- vessel-type-specific region mappings ----------
# Format: REGION_TO_PORTS_BY_VESSEL[vessel_type][region] = (default_port, [alternates])
# A region missing from a specific vessel map falls back to 'general' (which mirrors 'crude').

REGION_TO_PORTS_BY_VESSEL: dict[str, dict[str, tuple[str, list[str]]]] = {

    "crude": {
        "Australia / New Guinea Pacific": ("Gladstone",         ["Port Hedland", "Newcastle AU"]),
        "East Asia / SE Asia / Australia":("Singapore",         ["Ningbo-Zhoushan", "Map Ta Phut"]),
        "East Asia / SE Asia":            ("Ningbo-Zhoushan",   ["Singapore", "Dalian", "Qingdao", "Map Ta Phut"]),
        "East Asia -> NA West Coast":     ("Yokohama",          ["Dalian", "Ningbo-Zhoushan"]),
        "North America West Coast":       ("Long Beach",        ["Los Angeles", "Valdez"]),
        "Gulf of Mexico / Middle America":("Houston",           ["Corpus Christi", "New Orleans", "LOOP"]),
        "East Asia":                      ("Ningbo-Zhoushan",   ["Dalian", "Qingdao", "Yokohama"]),
        "SE Asia":                        ("Singapore",         ["Map Ta Phut", "Cilacap"]),
        "Southeast Asia":                 ("Singapore",         ["Map Ta Phut", "Cilacap"]),
        "Northeast Asia":                 ("Yokohama",          ["Ulsan", "Dalian"]),
        "South Asia":                     ("Sikka",             ["Mumbai (JNPT)", "Vizag"]),
        "Indian Ocean":                   ("Sikka",             ["Mumbai (JNPT)", "Colombo"]),
        "Persian Gulf":                   ("Ras Tanura",        ["Kharg Island", "Basra", "Mina Al Ahmadi"]),
        "Arabian Gulf":                   ("Ras Tanura",        ["Fujairah", "Kharg Island"]),
        "Middle East":                    ("Ras Tanura",        ["Fujairah", "Kharg Island"]),
        "Red Sea":                        ("Yanbu",             ["Suez (Red Sea side)"]),
        "Mediterranean":                  ("Ceyhan",            ["Sidi Kerir", "Augusta"]),
        "Black Sea":                      ("Novorossiysk",      []),
        "North Sea":                      ("Rotterdam",         ["Antwerp"]),
        "Atlantic":                       ("Rotterdam",         ["Houston"]),
        "Pacific":                        ("Long Beach",        ["Yokohama"]),
        "North Pacific":                  ("Yokohama",          ["Long Beach"]),
        "South Pacific":                  ("Gladstone",         ["Sydney"]),
        "Caribbean":                      ("Kingston",          ["LOOP"]),
        "Gulf of Mexico":                 ("Houston",           ["Corpus Christi", "LOOP", "New Orleans"]),
        "US East Coast":                  ("Houston",           ["New York / NJ", "Norfolk"]),
        "US West Coast":                  ("Long Beach",        ["Los Angeles", "Valdez"]),
        "South America East Coast":       ("Santos",            ["Buenos Aires"]),
        "South America West Coast":       ("Callao",            ["Valparaiso"]),
        "West Africa":                    ("Bonny",             ["Escravos", "Lagos"]),
        "East Africa":                    ("Mombasa",           []),
        "South Africa":                   ("Durban",            ["Cape Town"]),
        "Europe":                         ("Rotterdam",         ["Antwerp"]),
        "Northern Europe":                ("Rotterdam",         ["Hamburg"]),
        "Western Europe":                 ("Rotterdam",         ["Antwerp", "Le Havre"]),
        "West Europe":                    ("Rotterdam",         ["Antwerp", "Le Havre"]),
        "Java Sea":                       ("Cilacap",           ["Jakarta (Tanjung Priok)"]),
        "South China Sea":                ("Ho Chi Minh City",  ["Hong Kong"]),
        "East China Sea":                 ("Ningbo-Zhoushan",   ["Shanghai"]),
        "Yellow Sea":                     ("Qingdao",           ["Dalian"]),
        "Sea of Japan":                   ("Yokohama",          ["Ulsan"]),
        "Bay of Bengal":                  ("Vizag",             ["Chennai"]),
        "Arabian Sea":                    ("Sikka",             ["Mumbai (JNPT)", "Fujairah"]),
        "Makassar Strait":                ("Balikpapan",        ["Bontang LNG", "Makassar"]),
        "Molucca Sea":                    ("Bitung",            ["Ternate"]),
        "Banda Sea":                      ("Ternate",           ["Bitung"]),
        "Sulu Sea":                       ("Manila",            ["Cai Mep"]),
        "Celebes Sea":                    ("Bitung",            ["Manila"]),
        "Timor Sea":                      ("Dampier",           ["Port Hedland"]),
        "Arafura Sea":                    ("Dampier",           ["Tangguh LNG"]),
        "Coral Sea":                      ("Gladstone",         ["Brisbane"]),
        "Tasman Sea":                     ("Sydney",            ["Tauranga"]),
        "Philippine Sea":                 ("Manila",            ["Yokohama"]),
        "Australia":                      ("Gladstone",         ["Port Hedland"]),
        "New Zealand":                    ("Tauranga",          []),
    },

    "chemical": {
        "SE Asia":                        ("Map Ta Phut",       ["Singapore", "Pasir Gudang"]),
        "Southeast Asia":                 ("Map Ta Phut",       ["Singapore", "Pasir Gudang"]),
        "East Asia":                      ("Ulsan",             ["Yokkaichi", "Shanghai"]),
        "Northeast Asia":                 ("Yokkaichi",         ["Ulsan", "Yeosu"]),
        "South Asia":                     ("Mumbai (JNPT)",     ["Sikka"]),
        "Indian Ocean":                   ("Mumbai (JNPT)",     ["Colombo"]),
        "Persian Gulf":                   ("Jubail",            ["Mesaieed", "Sohar", "Fujairah"]),
        "Middle East":                    ("Jubail",            ["Fujairah", "Sohar"]),
        "Red Sea":                        ("Yanbu",             []),
        "Mediterranean":                  ("Tarragona",         ["Algeciras", "Augusta"]),
        "North Sea":                      ("Antwerp",           ["Rotterdam"]),
        "Europe":                         ("Antwerp",           ["Rotterdam", "Hamburg"]),
        "Northern Europe":                ("Antwerp",           ["Rotterdam"]),
        "Western Europe":                 ("Antwerp",           ["Rotterdam", "Le Havre"]),
        "West Europe":                    ("Antwerp",           ["Rotterdam", "Le Havre"]),
        "US East Coast":                  ("Houston",           ["New York / NJ"]),
        "US West Coast":                  ("Long Beach",        ["Los Angeles"]),
        "Gulf of Mexico":                 ("Houston",           ["Pascagoula", "Corpus Christi"]),
        "Caribbean":                      ("Houston",           ["Cartagena CO"]),
        "South America East Coast":       ("Santos",            []),
        "West Africa":                    ("Lagos",             ["Bonny"]),
        "South Africa":                   ("Durban",            []),
        "Australia":                      ("Brisbane",          ["Sydney"]),
        "Java Sea":                       ("Jakarta (Tanjung Priok)", ["Pasir Gudang"]),
        "South China Sea":                ("Hong Kong",         ["Ho Chi Minh City"]),
        "East China Sea":                 ("Shanghai",          []),
        "Yellow Sea":                     ("Tianjin",           ["Qingdao"]),
        "Bay of Bengal":                  ("Vizag",             []),
        "Arabian Sea":                    ("Mumbai (JNPT)",     ["Jubail"]),
        "Makassar Strait":                ("Balikpapan",        ["Makassar"]),
        "Molucca Sea":                    ("Bitung",            []),
        "Sulu Sea":                       ("Manila",            []),
        "Celebes Sea":                    ("Bitung",            []),
        "Coral Sea":                      ("Brisbane",          []),
        "Tasman Sea":                     ("Sydney",            []),
    },

    "gas": {  # LNG + LPG (use LNG terminals; LPG often co-located)
        "SE Asia":                        ("Bontang LNG",       ["Map Ta Phut", "Tangguh LNG"]),
        "Southeast Asia":                 ("Bontang LNG",       ["Tangguh LNG", "Map Ta Phut"]),
        "East Asia":                      ("Sodegaura LNG",     ["Futtsu LNG", "Tianjin LNG", "Senboku LNG"]),
        "Northeast Asia":                 ("Sodegaura LNG",     ["Futtsu LNG", "Incheon LNG"]),
        "Japan":                          ("Sodegaura LNG",     ["Futtsu LNG", "Senboku LNG"]),
        "Korea":                          ("Incheon LNG",       ["Yeosu"]),
        "China":                          ("Tianjin LNG",       ["Shanghai"]),
        "Persian Gulf":                   ("Ras Laffan LNG",    ["Mesaieed", "Jubail"]),
        "Middle East":                    ("Ras Laffan LNG",    ["Mesaieed"]),
        "Red Sea":                        ("Yanbu",             []),
        "Mediterranean":                  ("Sines",             ["Bilbao", "Piraeus"]),
        "Europe":                         ("Zeebrugge LNG",     ["Rotterdam", "Sines"]),
        "Northern Europe":                ("Zeebrugge LNG",     ["Rotterdam"]),
        "Western Europe":                 ("Zeebrugge LNG",     ["Rotterdam", "Bilbao"]),
        "West Europe":                    ("Zeebrugge LNG",     ["Rotterdam", "Bilbao"]),
        "North Sea":                      ("Zeebrugge LNG",     ["Rotterdam"]),
        "US East Coast":                  ("Cove Point LNG",    ["Sabine Pass LNG"]),
        "US West Coast":                  ("Long Beach",        []),
        "Gulf of Mexico":                 ("Sabine Pass LNG",   ["Freeport LNG", "Cameron LNG", "Corpus Christi"]),
        "Caribbean":                      ("Kingston",          []),
        "South America East Coast":       ("Santos",            []),
        "West Africa":                    ("Bonny",             ["Lagos"]),  # Bonny LNG
        "South Africa":                   ("Cape Town",         ["Durban"]),
        "Australia":                      ("Gladstone LNG",     ["Karratha LNG", "Dampier"]),
        "Australia / New Guinea Pacific": ("Gladstone LNG",     ["Karratha LNG"]),
        "South Asia":                     ("Mumbai (JNPT)",     ["Hambantota"]),
        "South China Sea":                ("Tangguh LNG",       []),
        "Java Sea":                       ("Bontang LNG",       []),
        "Makassar Strait":                ("Bontang LNG",       ["Balikpapan"]),
        "Molucca Sea":                    ("Tangguh LNG",       ["Bitung"]),
        "Banda Sea":                      ("Tangguh LNG",       []),
        "Arafura Sea":                    ("Tangguh LNG",       ["Karratha LNG"]),
        "Timor Sea":                      ("Karratha LNG",      ["Dampier"]),
        "Coral Sea":                      ("Gladstone LNG",     []),
    },

    "container": {
        "SE Asia":                        ("Singapore",         ["Port Klang", "Tanjung Pelepas", "Laem Chabang"]),
        "Southeast Asia":                 ("Singapore",         ["Port Klang", "Tanjung Pelepas", "Laem Chabang"]),
        "East Asia":                      ("Shanghai",          ["Ningbo-Zhoushan", "Shenzhen (Yantian)", "Hong Kong", "Busan"]),
        "Northeast Asia":                 ("Busan",             ["Shanghai", "Yokohama"]),
        "East Asia / SE Asia":            ("Shanghai",          ["Singapore", "Hong Kong"]),
        "East Asia -> NA West Coast":     ("Shanghai",          ["Busan", "Yokohama"]),
        "South Asia":                     ("Mundra",            ["Mumbai (JNPT)", "Colombo"]),
        "Indian Ocean":                   ("Colombo",           ["Mundra", "Hambantota"]),
        "Persian Gulf":                   ("Jebel Ali",         ["Khor Fakkan", "Sohar"]),
        "Middle East":                    ("Jebel Ali",         ["Khor Fakkan"]),
        "Red Sea":                        ("Port Said",         ["Suez (Red Sea side)"]),
        "Mediterranean":                  ("Algeciras",         ["Tanger Med", "Piraeus", "Valencia"]),
        "Black Sea":                      ("Istanbul",          ["Novorossiysk"]),
        "North Sea":                      ("Rotterdam",         ["Hamburg", "Antwerp"]),
        "Europe":                         ("Rotterdam",         ["Hamburg", "Antwerp"]),
        "Northern Europe":                ("Rotterdam",         ["Hamburg", "Bremerhaven", "Antwerp"]),
        "Western Europe":                 ("Rotterdam",         ["Antwerp", "Le Havre"]),
        "West Europe":                    ("Rotterdam",         ["Antwerp", "Le Havre"]),
        "North America West Coast":       ("Long Beach",        ["Los Angeles", "Oakland", "Seattle", "Vancouver BC"]),
        "US West Coast":                  ("Long Beach",        ["Los Angeles", "Oakland", "Seattle"]),
        "Gulf of Mexico / Middle America":("Houston",           ["Cartagena CO"]),
        "Gulf of Mexico":                 ("Houston",           []),
        "US East Coast":                  ("New York / NJ",     ["Savannah", "Charleston", "Norfolk"]),
        "Caribbean":                      ("Cartagena CO",      ["Kingston", "Panama (Atlantic)"]),
        "South America East Coast":       ("Santos",            ["Buenos Aires"]),
        "South America West Coast":       ("Callao",            ["Valparaiso"]),
        "West Africa":                    ("Lagos",             ["Tanger Med"]),
        "East Africa":                    ("Mombasa",           []),
        "South Africa":                   ("Durban",            ["Cape Town"]),
        "Australia":                      ("Sydney",            ["Melbourne", "Brisbane"]),
        "Australia / New Guinea Pacific": ("Brisbane",          ["Sydney", "Newcastle AU"]),
        "Pacific":                        ("Honolulu",          []),
        "North Pacific":                  ("Long Beach",        ["Yokohama", "Vancouver BC"]),
        "South Pacific":                  ("Sydney",            ["Tauranga"]),
        "Java Sea":                       ("Jakarta (Tanjung Priok)", ["Tanjung Pelepas"]),
        "South China Sea":                ("Hong Kong",         ["Shenzhen (Yantian)", "Cai Mep"]),
        "East China Sea":                 ("Shanghai",          ["Ningbo-Zhoushan", "Kaohsiung"]),
        "Yellow Sea":                     ("Qingdao",           ["Busan", "Dalian"]),
        "Bay of Bengal":                  ("Colombo",           ["Chennai", "Chittagong"]),
        "Arabian Sea":                    ("Mundra",            ["Mumbai (JNPT)", "Jebel Ali"]),
        "Makassar Strait":                ("Makassar",          ["Balikpapan"]),
        "Molucca Sea":                    ("Bitung",            []),
        "Sulu Sea":                       ("Manila",            []),
        "Celebes Sea":                    ("Bitung",            ["Manila"]),
        "Philippine Sea":                 ("Manila",            ["Kaohsiung"]),
        "Coral Sea":                      ("Brisbane",          ["Sydney"]),
        "Tasman Sea":                     ("Sydney",            ["Tauranga", "Melbourne"]),
    },
}

# `general` reuses the crude map (keeps backward compatibility)
REGION_TO_PORTS_BY_VESSEL["general"] = REGION_TO_PORTS_BY_VESSEL["crude"]


# ---------- keyword fallback by vessel type ----------
# Each entry: (keywords, port_name). First hit wins.
# If a vessel type has no specific entry for a keyword, we fall through to `general`.

_BASE_KEYWORDS = [
    (("alaska", "valdez"),                "Valdez"),
    (("hawaii", "honolulu"),              "Honolulu"),
    (("new zealand",),                    "Tauranga"),
    (("argentina",),                      "Buenos Aires"),
]

KEYWORD_FALLBACK_BY_VESSEL: dict[str, list[tuple[tuple[str, ...], str]]] = {

    "crude": [
        (("persian gulf", "arabian gulf", "middle east", "ras tanura", "kharg"), "Ras Tanura"),
        (("red sea",),                                  "Yanbu"),
        (("mediterranean",),                            "Ceyhan"),
        (("black sea",),                                "Novorossiysk"),
        (("north sea", "rotterdam"),                    "Rotterdam"),
        (("northern europe", "north europe", "western europe", "west europe", "baltic"), "Rotterdam"),
        (("west africa",),                              "Bonny"),
        (("east africa",),                              "Mombasa"),
        (("south africa",),                             "Durban"),
        (("caribbean", "jamaica"),                      "Kingston"),
        (("gulf of mexico", "gulf coast", "us gulf"),   "Houston"),
        (("us east", "east coast"),                     "Houston"),
        (("us west", "west coast", "na west", "north america west"), "Long Beach"),
        (("na east", "north america east"),             "Houston"),
        (("south america west", "sa west", "peru", "chile"), "Callao"),
        (("south america east", "sa east", "brazil"),   "Santos"),
        (("java sea", "java"),                          "Cilacap"),
        (("south china sea",),                          "Ho Chi Minh City"),
        (("east china sea",),                           "Ningbo-Zhoushan"),
        (("yellow sea",),                               "Qingdao"),
        (("sea of japan",),                             "Yokohama"),
        (("bay of bengal",),                            "Vizag"),
        (("arabian sea",),                              "Sikka"),
        (("makassar", "balikpapan"),                    "Balikpapan"),
        (("molucca", "moluccas", "maluku", "halmahera", "celebes", "sulawesi"), "Bitung"),
        (("banda sea", "arafura"),                      "Ternate"),
        (("timor",),                                    "Dampier"),
        (("coral sea",),                                "Gladstone"),
        (("tasman",),                                   "Sydney"),
        (("philippine sea",),                           "Manila"),
        (("sulu",),                                     "Manila"),
        (("borneo", "kalimantan"),                      "Balikpapan"),
        (("indonesia",),                                "Cilacap"),
        (("se asia", "southeast asia", "south east asia", "singapore", "malacca"), "Singapore"),
        (("east asia", "china", "north asia"),          "Ningbo-Zhoushan"),
        (("japan",),                                    "Yokohama"),
        (("korea",),                                    "Ulsan"),
        (("taiwan",),                                   "Kaohsiung"),
        (("philippines",),                              "Manila"),
        (("vietnam",),                                  "Ho Chi Minh City"),
        (("south asia", "india", "mumbai"),             "Sikka"),
        (("indian ocean",),                             "Sikka"),
        (("sri lanka",),                                "Colombo"),
        (("bangladesh",),                               "Chittagong"),
        (("australia", "new guinea"),                   "Gladstone"),
        (("panama",),                                   "Panama (Pacific)"),
        (("mexico",),                                   "Manzanillo MX"),
        (("pacific",),                                  "Honolulu"),
        (("atlantic",),                                 "Rotterdam"),
    ],

    "chemical": [
        (("persian gulf", "arabian gulf", "middle east"), "Jubail"),
        (("mediterranean",),                              "Tarragona"),
        (("north sea",),                                  "Antwerp"),
        (("northern europe", "north europe", "western europe", "west europe", "baltic"), "Antwerp"),
        (("gulf of mexico", "us gulf"),                   "Houston"),
        (("us east", "east coast"),                       "Houston"),
        (("us west", "west coast"),                       "Long Beach"),
        (("caribbean",),                                  "Houston"),
        (("south america east", "brazil"),                "Santos"),
        (("se asia", "southeast asia"),                   "Map Ta Phut"),
        (("east asia", "china"),                          "Ulsan"),
        (("japan",),                                      "Yokkaichi"),
        (("korea",),                                      "Yeosu"),
        (("south asia", "india"),                         "Mumbai (JNPT)"),
        (("indian ocean",),                               "Mumbai (JNPT)"),
        (("makassar", "balikpapan"),                      "Balikpapan"),
        (("molucca", "moluccas", "maluku", "halmahera", "celebes", "sulawesi"), "Bitung"),
        (("indonesia", "java sea"),                       "Jakarta (Tanjung Priok)"),
        (("south china sea",),                            "Hong Kong"),
        (("east china sea",),                             "Shanghai"),
        (("yellow sea",),                                 "Tianjin"),
        (("bay of bengal",),                              "Vizag"),
        (("arabian sea",),                                "Mumbai (JNPT)"),
        (("west africa", "nigeria"),                      "Lagos"),
        (("south africa",),                               "Durban"),
        (("australia",),                                  "Brisbane"),
    ],

    "gas": [
        (("persian gulf", "arabian gulf", "qatar"),       "Ras Laffan LNG"),
        (("middle east",),                                "Ras Laffan LNG"),
        (("mediterranean",),                              "Sines"),
        (("north sea",),                                  "Zeebrugge LNG"),
        (("northern europe", "north europe", "western europe", "west europe", "baltic"), "Zeebrugge LNG"),
        (("gulf of mexico", "us gulf"),                   "Sabine Pass LNG"),
        (("us east", "east coast"),                       "Cove Point LNG"),
        (("us west", "west coast"),                       "Long Beach"),
        (("se asia", "southeast asia"),                   "Bontang LNG"),
        (("east asia",),                                  "Sodegaura LNG"),
        (("japan",),                                      "Sodegaura LNG"),
        (("korea",),                                      "Incheon LNG"),
        (("china",),                                      "Tianjin LNG"),
        (("south asia", "india"),                         "Mumbai (JNPT)"),
        (("makassar", "balikpapan"),                      "Bontang LNG"),
        (("molucca", "moluccas", "maluku", "halmahera", "banda", "arafura"), "Tangguh LNG"),
        (("celebes", "sulawesi"),                         "Bontang LNG"),
        (("timor",),                                      "Karratha LNG"),
        (("coral sea",),                                  "Gladstone LNG"),
        (("indonesia", "java sea"),                       "Bontang LNG"),
        (("west africa", "nigeria"),                      "Bonny"),
        (("south africa",),                               "Cape Town"),
        (("australia", "new guinea"),                     "Gladstone LNG"),
        (("south america east", "brazil"),                "Santos"),
        (("south china sea",),                            "Tangguh LNG"),
    ],

    "container": [
        (("persian gulf", "arabian gulf", "middle east"), "Jebel Ali"),
        (("red sea",),                                    "Port Said"),
        (("mediterranean",),                              "Algeciras"),
        (("black sea",),                                  "Istanbul"),
        (("north sea",),                                  "Rotterdam"),
        (("northern europe", "north europe"),             "Rotterdam"),
        (("western europe", "west europe", "baltic"),     "Rotterdam"),
        (("gulf of mexico", "us gulf"),                   "Houston"),
        (("us east", "east coast"),                       "New York / NJ"),
        (("us west", "west coast", "na west", "north america west"), "Long Beach"),
        (("caribbean",),                                  "Cartagena CO"),
        (("south america east", "brazil"),                "Santos"),
        (("south america west", "peru", "chile"),         "Callao"),
        (("se asia", "southeast asia", "singapore", "malacca"), "Singapore"),
        (("east asia", "china"),                          "Shanghai"),
        (("japan",),                                      "Yokohama"),
        (("korea",),                                      "Busan"),
        (("taiwan",),                                     "Kaohsiung"),
        (("vietnam",),                                    "Cai Mep"),
        (("philippines",),                                "Manila"),
        (("makassar", "balikpapan"),                      "Makassar"),
        (("molucca", "moluccas", "maluku", "halmahera", "celebes", "sulawesi"), "Bitung"),
        (("sulu",),                                       "Manila"),
        (("philippine sea",),                             "Manila"),
        (("coral sea",),                                  "Brisbane"),
        (("tasman",),                                     "Sydney"),
        (("indonesia", "java sea"),                       "Jakarta (Tanjung Priok)"),
        (("south asia", "india"),                         "Mundra"),
        (("indian ocean", "sri lanka"),                   "Colombo"),
        (("bangladesh",),                                 "Chittagong"),
        (("south china sea",),                            "Hong Kong"),
        (("east china sea",),                             "Shanghai"),
        (("yellow sea",),                                 "Qingdao"),
        (("bay of bengal",),                              "Colombo"),
        (("arabian sea",),                                "Mundra"),
        (("west africa", "nigeria"),                      "Lagos"),
        (("east africa",),                                "Mombasa"),
        (("south africa",),                               "Durban"),
        (("australia",),                                  "Sydney"),
        (("panama",),                                     "Panama (Atlantic)"),
        (("pacific",),                                    "Honolulu"),
    ],
}

# `general` reuses `crude` keyword fallback
KEYWORD_FALLBACK_BY_VESSEL["general"] = KEYWORD_FALLBACK_BY_VESSEL["crude"]


VESSEL_TYPES = ["crude", "chemical", "gas", "container", "general"]

VESSEL_TYPE_LABELS = {
    "crude":     "Crude oil tanker (VLCC / Suezmax / Aframax)",
    "chemical":  "Chemical / product tanker",
    "gas":       "Gas carrier (LNG / LPG)",
    "container": "Container ship",
    "general":   "Khác / chưa xác định (dùng crude làm fallback)",
}


# ---------- resolution ----------

def _normalize(s: str) -> str:
    return " ".join(
        s.lower()
        .replace("_", " ")
        .replace("→", "->")
        .replace("–", "-")
        .replace("—", "-")
        .split()
    )


def _index_for(vessel_type: str):
    """Pre-built case-insensitive index for the given vessel-type region map."""
    region_map = REGION_TO_PORTS_BY_VESSEL[vessel_type]
    return {_normalize(k): k for k in region_map}


def resolve_port(region: str, vessel_type: str = "crude"):
    """Return (port_name, lon, lat) for a (region, vessel_type), or None if unknown.

    Resolution order:
      1. Exact match in vessel-specific region map
      2. Case-insensitive normalized match in vessel-specific map
      3. Keyword fallback for the vessel type
      4. Same 3 steps against `general` (crude) as fallback
    """
    if not region or not region.strip():
        return None

    vessel_type = vessel_type if vessel_type in REGION_TO_PORTS_BY_VESSEL else "general"

    for vt in (vessel_type, "general"):
        region_map = REGION_TO_PORTS_BY_VESSEL[vt]
        norm_index = _index_for(vt)

        entry = region_map.get(region.strip())
        if entry:
            name = entry[0]
            return name, *PORTS[name]

        norm = _normalize(region)
        if norm in norm_index:
            name = region_map[norm_index[norm]][0]
            return name, *PORTS[name]

        for keywords, port_name in KEYWORD_FALLBACK_BY_VESSEL[vt]:
            if any(kw in norm for kw in keywords):
                return port_name, *PORTS[port_name]

        for keywords, port_name in _BASE_KEYWORDS:
            if any(kw in norm for kw in keywords):
                return port_name, *PORTS[port_name]

        if vt == vessel_type and vessel_type == "general":
            break  # don't double-check general

    return None
