"""One-off generator for config/cities.json (top ~100 Indian cities).

Keeps the city dataset in one editable place. Computes a URL slug (id) from the
name, attaches a coarse climate (only 'semi_arid' affects the mock positivity
sparseness), and writes config/cities.json. Validates that every coordinate sits
inside India's bounding box so a typo surfaces loudly.

NOTE: coordinates are city-centroid approximations, good to ~0.05 deg, which is
fine for a ~50 km NASA POWER grid and nearest-city snapping. Do a QA pass against
an authoritative gazetteer before public launch (tracked in CLAUDE.md).

Run:  python scripts/gen_cities.py
"""
from __future__ import annotations

import json
import os
import re
import sys

# name, state, lat, lon, climate
CITIES = [
    ("Mumbai", "Maharashtra", 19.0760, 72.8777, "tropical_wet"),
    ("Delhi", "Delhi", 28.7041, 77.1025, "semi_arid"),
    ("Bengaluru", "Karnataka", 12.9716, 77.5946, "tropical_savanna"),
    ("Hyderabad", "Telangana", 17.3850, 78.4867, "tropical_savanna"),
    ("Ahmedabad", "Gujarat", 23.0225, 72.5714, "semi_arid"),
    ("Chennai", "Tamil Nadu", 13.0827, 80.2707, "tropical_wet"),
    ("Kolkata", "West Bengal", 22.5726, 88.3639, "tropical_wet"),
    ("Surat", "Gujarat", 21.1702, 72.8311, "tropical_savanna"),
    ("Pune", "Maharashtra", 18.5204, 73.8567, "tropical_savanna"),
    ("Jaipur", "Rajasthan", 26.9124, 75.7873, "semi_arid"),
    ("Lucknow", "Uttar Pradesh", 26.8467, 80.9462, "humid_subtropical"),
    ("Kanpur", "Uttar Pradesh", 26.4499, 80.3319, "humid_subtropical"),
    ("Nagpur", "Maharashtra", 21.1458, 79.0882, "tropical_savanna"),
    ("Indore", "Madhya Pradesh", 22.7196, 75.8577, "semi_arid"),
    ("Thane", "Maharashtra", 19.2183, 72.9781, "tropical_wet"),
    ("Bhopal", "Madhya Pradesh", 23.2599, 77.4126, "humid_subtropical"),
    ("Visakhapatnam", "Andhra Pradesh", 17.6868, 83.2185, "tropical_wet"),
    ("Patna", "Bihar", 25.5941, 85.1376, "humid_subtropical"),
    ("Vadodara", "Gujarat", 22.3072, 73.1812, "tropical_savanna"),
    ("Ghaziabad", "Uttar Pradesh", 28.6692, 77.4538, "semi_arid"),
    ("Ludhiana", "Punjab", 30.9010, 75.8573, "semi_arid"),
    ("Agra", "Uttar Pradesh", 27.1767, 78.0081, "semi_arid"),
    ("Nashik", "Maharashtra", 19.9975, 73.7898, "tropical_savanna"),
    ("Faridabad", "Haryana", 28.4089, 77.3178, "semi_arid"),
    ("Meerut", "Uttar Pradesh", 28.9845, 77.7064, "humid_subtropical"),
    ("Rajkot", "Gujarat", 22.3039, 70.8022, "semi_arid"),
    ("Varanasi", "Uttar Pradesh", 25.3176, 82.9739, "humid_subtropical"),
    ("Srinagar", "Jammu and Kashmir", 34.0837, 74.7973, "temperate"),
    ("Aurangabad", "Maharashtra", 19.8762, 75.3433, "tropical_savanna"),
    ("Dhanbad", "Jharkhand", 23.7957, 86.4304, "humid_subtropical"),
    ("Amritsar", "Punjab", 31.6340, 74.8723, "semi_arid"),
    ("Prayagraj", "Uttar Pradesh", 25.4358, 81.8463, "humid_subtropical"),
    ("Ranchi", "Jharkhand", 23.3441, 85.3096, "humid_subtropical"),
    ("Howrah", "West Bengal", 22.5958, 88.2636, "tropical_wet"),
    ("Coimbatore", "Tamil Nadu", 11.0168, 76.9558, "tropical_savanna"),
    ("Jabalpur", "Madhya Pradesh", 23.1815, 79.9864, "humid_subtropical"),
    ("Gwalior", "Madhya Pradesh", 26.2183, 78.1828, "semi_arid"),
    ("Vijayawada", "Andhra Pradesh", 16.5062, 80.6480, "tropical_savanna"),
    ("Jodhpur", "Rajasthan", 26.2389, 73.0243, "semi_arid"),
    ("Madurai", "Tamil Nadu", 9.9252, 78.1198, "tropical_savanna"),
    ("Raipur", "Chhattisgarh", 21.2514, 81.6296, "tropical_savanna"),
    ("Kota", "Rajasthan", 25.2138, 75.8648, "semi_arid"),
    ("Guwahati", "Assam", 26.1445, 91.7362, "humid_subtropical"),
    ("Chandigarh", "Chandigarh", 30.7333, 76.7794, "humid_subtropical"),
    ("Solapur", "Maharashtra", 17.6599, 75.9064, "semi_arid"),
    ("Hubballi", "Karnataka", 15.3647, 75.1240, "tropical_savanna"),
    ("Mysuru", "Karnataka", 12.2958, 76.6394, "tropical_savanna"),
    ("Tiruchirappalli", "Tamil Nadu", 10.7905, 78.7047, "tropical_savanna"),
    ("Bareilly", "Uttar Pradesh", 28.3670, 79.4304, "humid_subtropical"),
    ("Aligarh", "Uttar Pradesh", 27.8974, 78.0880, "semi_arid"),
    ("Tiruppur", "Tamil Nadu", 11.1085, 77.3411, "tropical_savanna"),
    ("Gurugram", "Haryana", 28.4595, 77.0266, "semi_arid"),
    ("Moradabad", "Uttar Pradesh", 28.8386, 78.7733, "humid_subtropical"),
    ("Jalandhar", "Punjab", 31.3260, 75.5762, "semi_arid"),
    ("Bhubaneswar", "Odisha", 20.2961, 85.8245, "tropical_wet"),
    ("Salem", "Tamil Nadu", 11.6643, 78.1460, "tropical_savanna"),
    ("Warangal", "Telangana", 17.9689, 79.5941, "tropical_savanna"),
    ("Guntur", "Andhra Pradesh", 16.3067, 80.4365, "tropical_savanna"),
    ("Bhiwandi", "Maharashtra", 19.2967, 73.0631, "tropical_wet"),
    ("Saharanpur", "Uttar Pradesh", 29.9680, 77.5552, "humid_subtropical"),
    ("Gorakhpur", "Uttar Pradesh", 26.7606, 83.3732, "humid_subtropical"),
    ("Bikaner", "Rajasthan", 28.0229, 73.3119, "semi_arid"),
    ("Amravati", "Maharashtra", 20.9374, 77.7796, "tropical_savanna"),
    ("Noida", "Uttar Pradesh", 28.5355, 77.3910, "semi_arid"),
    ("Jamshedpur", "Jharkhand", 22.8046, 86.2029, "humid_subtropical"),
    ("Bhilai", "Chhattisgarh", 21.1938, 81.3509, "tropical_savanna"),
    ("Cuttack", "Odisha", 20.4625, 85.8830, "tropical_wet"),
    ("Firozabad", "Uttar Pradesh", 27.1591, 78.3958, "semi_arid"),
    ("Kochi", "Kerala", 9.9312, 76.2673, "tropical_wet"),
    ("Nellore", "Andhra Pradesh", 14.4426, 79.9865, "tropical_savanna"),
    ("Bhavnagar", "Gujarat", 21.7645, 72.1519, "semi_arid"),
    ("Dehradun", "Uttarakhand", 30.3165, 78.0322, "humid_subtropical"),
    ("Durgapur", "West Bengal", 23.5204, 87.3119, "humid_subtropical"),
    ("Asansol", "West Bengal", 23.6839, 86.9523, "humid_subtropical"),
    ("Rourkela", "Odisha", 22.2604, 84.8536, "tropical_savanna"),
    ("Nanded", "Maharashtra", 19.1383, 77.3210, "semi_arid"),
    ("Kolhapur", "Maharashtra", 16.7050, 74.2433, "tropical_savanna"),
    ("Ajmer", "Rajasthan", 26.4499, 74.6399, "semi_arid"),
    ("Akola", "Maharashtra", 20.7002, 77.0082, "tropical_savanna"),
    ("Gulbarga", "Karnataka", 17.3297, 76.8343, "semi_arid"),
    ("Jamnagar", "Gujarat", 22.4707, 70.0577, "semi_arid"),
    ("Ujjain", "Madhya Pradesh", 23.1765, 75.7885, "semi_arid"),
    ("Siliguri", "West Bengal", 26.7271, 88.3953, "humid_subtropical"),
    ("Jhansi", "Uttar Pradesh", 25.4484, 78.5685, "semi_arid"),
    ("Jammu", "Jammu and Kashmir", 32.7266, 74.8570, "humid_subtropical"),
    ("Mangaluru", "Karnataka", 12.9141, 74.8560, "tropical_wet"),
    ("Erode", "Tamil Nadu", 11.3410, 77.7172, "tropical_savanna"),
    ("Belagavi", "Karnataka", 15.8497, 74.4977, "tropical_savanna"),
    ("Tirunelveli", "Tamil Nadu", 8.7139, 77.7567, "tropical_savanna"),
    ("Gaya", "Bihar", 24.7969, 85.0002, "humid_subtropical"),
    ("Udaipur", "Rajasthan", 24.5854, 73.7125, "semi_arid"),
    ("Tirupati", "Andhra Pradesh", 13.6288, 79.4192, "tropical_savanna"),
    ("Davanagere", "Karnataka", 14.4644, 75.9218, "tropical_savanna"),
    ("Kozhikode", "Kerala", 11.2588, 75.7804, "tropical_wet"),
    ("Kurnool", "Andhra Pradesh", 15.8281, 78.0373, "semi_arid"),
    ("Bokaro", "Jharkhand", 23.6693, 86.1511, "humid_subtropical"),
    ("Bellary", "Karnataka", 15.1394, 76.9214, "semi_arid"),
    ("Patiala", "Punjab", 30.3398, 76.3869, "semi_arid"),
    ("Agartala", "Tripura", 23.8315, 91.2868, "tropical_wet"),
    ("Bhagalpur", "Bihar", 25.2425, 86.9842, "humid_subtropical"),
    ("Muzaffarnagar", "Uttar Pradesh", 29.4727, 77.7085, "humid_subtropical"),
    ("Latur", "Maharashtra", 18.4088, 76.5604, "semi_arid"),
    ("Dhule", "Maharashtra", 20.9042, 74.7749, "semi_arid"),
    ("Rohtak", "Haryana", 28.8955, 76.6066, "semi_arid"),
    ("Korba", "Chhattisgarh", 22.3595, 82.7501, "tropical_savanna"),
    ("Bhilwara", "Rajasthan", 25.3463, 74.6364, "semi_arid"),
    ("Brahmapur", "Odisha", 19.3150, 84.7941, "tropical_wet"),
    ("Muzaffarpur", "Bihar", 26.1209, 85.3647, "humid_subtropical"),
    ("Mathura", "Uttar Pradesh", 27.4924, 77.6737, "semi_arid"),
    ("Kollam", "Kerala", 8.8932, 76.6141, "tropical_wet"),
    ("Bilaspur", "Chhattisgarh", 22.0797, 82.1409, "tropical_savanna"),
    ("Shahjahanpur", "Uttar Pradesh", 27.8815, 79.9119, "humid_subtropical"),
    ("Thrissur", "Kerala", 10.5276, 76.2144, "tropical_wet"),
    ("Alwar", "Rajasthan", 27.5530, 76.6346, "semi_arid"),
    ("Kakinada", "Andhra Pradesh", 16.9891, 82.2475, "tropical_wet"),
    ("Nizamabad", "Telangana", 18.6725, 78.0941, "tropical_savanna"),
    ("Panipat", "Haryana", 29.3909, 76.9635, "semi_arid"),
    ("Darbhanga", "Bihar", 26.1542, 85.8918, "humid_subtropical"),
    ("Aizawl", "Mizoram", 23.7271, 92.7176, "humid_subtropical"),

    # --- next ~100 cities (added 2026-06-06 to reach ~220; coords are ~0.05 deg
    # approximations like the originals, QA against a gazetteer before launch) ---
    # missing state / UT capitals
    ("Thiruvananthapuram", "Kerala", 8.5241, 76.9366, "tropical_wet"),
    ("Gandhinagar", "Gujarat", 23.2156, 72.6369, "semi_arid"),
    ("Panaji", "Goa", 15.4909, 73.8278, "tropical_wet"),
    ("Shimla", "Himachal Pradesh", 31.1048, 77.1734, "temperate"),
    ("Imphal", "Manipur", 24.8170, 93.9368, "humid_subtropical"),
    ("Shillong", "Meghalaya", 25.5788, 91.8933, "humid_subtropical"),
    ("Kohima", "Nagaland", 25.6751, 94.1086, "humid_subtropical"),
    ("Itanagar", "Arunachal Pradesh", 27.0844, 93.6053, "humid_subtropical"),
    ("Gangtok", "Sikkim", 27.3389, 88.6065, "temperate"),
    ("Puducherry", "Puducherry", 11.9416, 79.8083, "tropical_wet"),
    ("Port Blair", "Andaman and Nicobar Islands", 11.6234, 92.7265, "tropical_wet"),
    ("Leh", "Ladakh", 34.1526, 77.5770, "temperate"),
    ("Daman", "Dadra and Nagar Haveli and Daman and Diu", 20.3974, 72.8328, "tropical_wet"),
    ("Silvassa", "Dadra and Nagar Haveli and Daman and Diu", 20.2738, 73.0140, "tropical_wet"),
    # Maharashtra
    ("Vasai-Virar", "Maharashtra", 19.3919, 72.8397, "tropical_wet"),
    ("Kalyan-Dombivli", "Maharashtra", 19.2403, 73.1305, "tropical_wet"),
    ("Mira-Bhayandar", "Maharashtra", 19.2952, 72.8544, "tropical_wet"),
    ("Sangli", "Maharashtra", 16.8524, 74.5815, "tropical_savanna"),
    ("Jalgaon", "Maharashtra", 21.0077, 75.5626, "tropical_savanna"),
    ("Malegaon", "Maharashtra", 20.5579, 74.5089, "semi_arid"),
    ("Ulhasnagar", "Maharashtra", 19.2215, 73.1645, "tropical_wet"),
    ("Ahmednagar", "Maharashtra", 19.0948, 74.7480, "semi_arid"),
    ("Chandrapur", "Maharashtra", 19.9615, 79.2961, "tropical_savanna"),
    ("Parbhani", "Maharashtra", 19.2704, 76.7600, "semi_arid"),
    ("Satara", "Maharashtra", 17.6805, 73.9933, "tropical_savanna"),
    # Uttar Pradesh
    ("Rampur", "Uttar Pradesh", 28.7983, 79.0250, "humid_subtropical"),
    ("Hapur", "Uttar Pradesh", 28.7306, 77.7759, "semi_arid"),
    ("Mirzapur", "Uttar Pradesh", 25.1337, 82.5645, "humid_subtropical"),
    ("Etawah", "Uttar Pradesh", 26.7855, 79.0150, "semi_arid"),
    ("Bulandshahr", "Uttar Pradesh", 28.4070, 77.8498, "semi_arid"),
    ("Sambhal", "Uttar Pradesh", 28.5904, 78.5718, "humid_subtropical"),
    ("Amroha", "Uttar Pradesh", 28.9023, 78.4677, "humid_subtropical"),
    ("Hardoi", "Uttar Pradesh", 27.3984, 80.1318, "humid_subtropical"),
    ("Fatehpur", "Uttar Pradesh", 25.9304, 80.8138, "humid_subtropical"),
    ("Raebareli", "Uttar Pradesh", 26.2309, 81.2337, "humid_subtropical"),
    ("Sitapur", "Uttar Pradesh", 27.5677, 80.6829, "humid_subtropical"),
    ("Unnao", "Uttar Pradesh", 26.5470, 80.4878, "humid_subtropical"),
    ("Budaun", "Uttar Pradesh", 28.0362, 79.1208, "humid_subtropical"),
    ("Loni", "Uttar Pradesh", 28.7515, 77.2885, "semi_arid"),
    # Bihar
    ("Bihar Sharif", "Bihar", 25.2003, 85.5236, "humid_subtropical"),
    ("Arrah", "Bihar", 25.5541, 84.6634, "humid_subtropical"),
    ("Begusarai", "Bihar", 25.4182, 86.1272, "humid_subtropical"),
    ("Purnia", "Bihar", 25.7771, 87.4753, "humid_subtropical"),
    ("Katihar", "Bihar", 25.5391, 87.5747, "humid_subtropical"),
    ("Chhapra", "Bihar", 25.7811, 84.7475, "humid_subtropical"),
    # West Bengal
    ("Bardhaman", "West Bengal", 23.2324, 87.8615, "humid_subtropical"),
    ("Malda", "West Bengal", 25.0119, 88.1433, "humid_subtropical"),
    ("Baharampur", "West Bengal", 24.1048, 88.2518, "tropical_wet"),
    ("Kharagpur", "West Bengal", 22.3460, 87.2320, "tropical_wet"),
    ("Haldia", "West Bengal", 22.0667, 88.0698, "tropical_wet"),
    # Rajasthan
    ("Sikar", "Rajasthan", 27.6094, 75.1399, "semi_arid"),
    ("Sri Ganganagar", "Rajasthan", 29.9094, 73.8800, "semi_arid"),
    ("Pali", "Rajasthan", 25.7711, 73.3234, "semi_arid"),
    ("Bharatpur", "Rajasthan", 27.2173, 77.4895, "semi_arid"),
    ("Hanumangarh", "Rajasthan", 29.5816, 74.3294, "semi_arid"),
    # Madhya Pradesh
    ("Sagar", "Madhya Pradesh", 23.8388, 78.7378, "humid_subtropical"),
    ("Ratlam", "Madhya Pradesh", 23.3315, 75.0367, "semi_arid"),
    ("Satna", "Madhya Pradesh", 24.6005, 80.8322, "humid_subtropical"),
    ("Rewa", "Madhya Pradesh", 24.5362, 81.3037, "humid_subtropical"),
    ("Dewas", "Madhya Pradesh", 22.9676, 76.0534, "semi_arid"),
    ("Katni", "Madhya Pradesh", 23.8338, 80.4001, "humid_subtropical"),
    ("Singrauli", "Madhya Pradesh", 24.1997, 82.6753, "humid_subtropical"),
    ("Khandwa", "Madhya Pradesh", 21.8257, 76.3522, "tropical_savanna"),
    # Gujarat
    ("Junagadh", "Gujarat", 21.5222, 70.4579, "semi_arid"),
    ("Gandhidham", "Gujarat", 23.0753, 70.1337, "semi_arid"),
    ("Anand", "Gujarat", 22.5645, 72.9289, "tropical_savanna"),
    ("Nadiad", "Gujarat", 22.6939, 72.8615, "tropical_savanna"),
    ("Morbi", "Gujarat", 22.8173, 70.8377, "semi_arid"),
    ("Bharuch", "Gujarat", 21.7051, 72.9959, "tropical_savanna"),
    ("Navsari", "Gujarat", 20.9467, 72.9520, "tropical_wet"),
    # Karnataka
    ("Shivamogga", "Karnataka", 13.9299, 75.5681, "tropical_savanna"),
    ("Tumakuru", "Karnataka", 13.3409, 77.1010, "tropical_savanna"),
    ("Vijayapura", "Karnataka", 16.8302, 75.7100, "semi_arid"),
    ("Raichur", "Karnataka", 16.2076, 77.3463, "semi_arid"),
    ("Udupi", "Karnataka", 13.3409, 74.7421, "tropical_wet"),
    ("Hassan", "Karnataka", 13.0072, 76.0962, "tropical_savanna"),
    # Tamil Nadu
    ("Vellore", "Tamil Nadu", 12.9165, 79.1325, "tropical_savanna"),
    ("Thoothukudi", "Tamil Nadu", 8.7642, 78.1348, "semi_arid"),
    ("Dindigul", "Tamil Nadu", 10.3624, 77.9695, "tropical_savanna"),
    ("Thanjavur", "Tamil Nadu", 10.7870, 79.1378, "tropical_savanna"),
    ("Nagercoil", "Tamil Nadu", 8.1833, 77.4119, "tropical_wet"),
    ("Kanchipuram", "Tamil Nadu", 12.8342, 79.7036, "tropical_savanna"),
    ("Hosur", "Tamil Nadu", 12.7409, 77.8253, "tropical_savanna"),
    # Andhra Pradesh / Telangana
    ("Rajahmundry", "Andhra Pradesh", 17.0005, 81.8040, "tropical_wet"),
    ("Kadapa", "Andhra Pradesh", 14.4673, 78.8242, "semi_arid"),
    ("Anantapur", "Andhra Pradesh", 14.6819, 77.6006, "semi_arid"),
    ("Eluru", "Andhra Pradesh", 16.7107, 81.0952, "tropical_savanna"),
    ("Ongole", "Andhra Pradesh", 15.5057, 80.0499, "tropical_savanna"),
    ("Khammam", "Telangana", 17.2473, 80.1514, "tropical_savanna"),
    ("Karimnagar", "Telangana", 18.4386, 79.1288, "tropical_savanna"),
    ("Ramagundam", "Telangana", 18.7600, 79.4740, "tropical_savanna"),
    # Kerala
    ("Kannur", "Kerala", 11.8745, 75.3704, "tropical_wet"),
    ("Kottayam", "Kerala", 9.5916, 76.5222, "tropical_wet"),
    ("Palakkad", "Kerala", 10.7867, 76.6548, "tropical_wet"),
    ("Alappuzha", "Kerala", 9.4981, 76.3388, "tropical_wet"),
    # Odisha / Haryana / Punjab / Uttarakhand / Assam / Jharkhand / Chhattisgarh
    ("Sambalpur", "Odisha", 21.4669, 83.9812, "tropical_savanna"),
    ("Puri", "Odisha", 19.8135, 85.8312, "tropical_wet"),
    ("Hisar", "Haryana", 29.1492, 75.7217, "semi_arid"),
    ("Karnal", "Haryana", 29.6857, 76.9905, "semi_arid"),
    ("Ambala", "Haryana", 30.3782, 76.7767, "humid_subtropical"),
    ("Bathinda", "Punjab", 30.2110, 74.9455, "semi_arid"),
    ("Mohali", "Punjab", 30.7046, 76.7179, "humid_subtropical"),
    ("Haridwar", "Uttarakhand", 29.9457, 78.1642, "humid_subtropical"),
    ("Haldwani", "Uttarakhand", 29.2183, 79.5130, "humid_subtropical"),
    ("Dibrugarh", "Assam", 27.4728, 94.9120, "humid_subtropical"),
    ("Silchar", "Assam", 24.8333, 92.7789, "humid_subtropical"),
    ("Deoghar", "Jharkhand", 24.4823, 86.6965, "humid_subtropical"),
    ("Hazaribagh", "Jharkhand", 23.9925, 85.3637, "humid_subtropical"),
    ("Raigarh", "Chhattisgarh", 21.8974, 83.3950, "tropical_savanna"),
]

ALIASES = {
    "bengaluru": ["bangalore"],
    "mumbai": ["bombay"],
    "kolkata": ["calcutta"],
    "chennai": ["madras"],
    "prayagraj": ["allahabad"],
    "gurugram": ["gurgaon"],
    "puducherry": ["pondicherry"],
    "mysuru": ["mysore"],
    "hubballi": ["hubli", "dharwad"],
    "mangaluru": ["mangalore"],
    "belagavi": ["belgaum"],
    "gulbarga": ["kalaburagi"],
    "brahmapur": ["berhampur"],
    "vadodara": ["baroda"],
    "thiruvananthapuram": ["trivandrum"],
    "vijayapura": ["bijapur"],
    "thoothukudi": ["tuticorin"],
    "shivamogga": ["shimoga"],
    "tumakuru": ["tumkur"],
    "bardhaman": ["burdwan"],
    "baharampur": ["berhampore"],
    "kalyan-dombivli": ["kalyan", "dombivli"],
    "vasai-virar": ["vasai", "virar"],
    "mira-bhayandar": ["mira road"],
}

# India bounding box (loose) for the sanity check.
LAT_RANGE = (6.0, 37.5)
LON_RANGE = (68.0, 97.5)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# Project scope LOCKED to cities with PharmEasy lab-positivity data (2026-06-16, user decision).
# These 19 had NO lab data in the 2025 season; dropping them takes the config from 228 -> 209.
# The 3 satellite metros among them (kalyan-dombivli, mira-bhayandar, vasai-virar) are FOLDED into
# their parent metro for lab routing (see data/citymap/manual_aliases.csv: Kalyan-Dombivli->Thane;
# Mira-Bhayandar / Vasai-Virar->Mumbai). If a dropped city later gains lab data, remove it from here.
DROP_NO_LAB_DATA = {
    "aizawl", "bhavnagar", "gangtok", "imphal", "itanagar", "kalyan-dombivli", "kohima", "leh",
    "loni", "malegaon", "mira-bhayandar", "morbi", "sambhal", "shillong", "shimla", "shivamogga",
    "silchar", "ulhasnagar", "vasai-virar",
}


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "config", "cities.json")

    seen, cities, errors = set(), [], []
    for name, state, lat, lon, climate in CITIES:
        cid = slugify(name)
        if cid in DROP_NO_LAB_DATA:
            continue
        if cid in seen:
            errors.append(f"duplicate id '{cid}' ({name})")
            continue
        seen.add(cid)
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
            errors.append(f"{name}: coord out of India bbox ({lat}, {lon})")
        entry = {"id": cid, "name": name, "state": state, "lat": lat, "lon": lon, "climate": climate}
        if cid in ALIASES:
            entry["aliases"] = ALIASES[cid]
        cities.append(entry)

    if errors:
        print("ABORT: city data problems:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1

    payload = {
        "_comment": (
            "Top Indian cities for Fever Watch (generated by scripts/gen_cities.py). "
            "Detected location snaps to the NEAREST centroid here; the picked city is a "
            "changeable default, never a hard lock. Coordinates are ~0.05 deg approximations; "
            "QA against an authoritative gazetteer before launch."
        ),
        "count": len(cities),
        "cities": cities,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {out}  ({len(cities)} cities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
