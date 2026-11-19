"""Leaf Identifier - Flask backend.

Flow:
  1. Clean up and resize the uploaded leaf image (Pillow).
  2. Pl@ntNet API identifies the plant from the leaf. No result or low score
     means the image is not a leaf -> "Upload the image of leaf only."
  3. Wikipedia Knowledge Engine extracts rich botanical summary, medicinal benefits,
     culinary uses, domestic air-purifying value, plant care, and cautions.
  4. Built-in Botanical Knowledge Base guarantees comprehensive on-page uses and
     benefits for every plant family and genus, even when Wikipedia lacks sections.
  5. (Optional) Google Lens via SerpApi provides visually similar specimens.
"""
import base64
import io
import os
import re

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from PIL import Image, UnidentifiedImageError

load_dotenv()

PLANTNET_KEY = os.getenv("PLANTNET_API_KEY", "")
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "")
IMGBB_KEY = os.getenv("IMGBB_API_KEY", "")
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.20"))
MAX_UPLOAD_MB = 8
NOT_LEAF_MESSAGE = "Upload the image of leaf only."
UA = {"User-Agent": "LeafIdentifier/2.0 (botanical student project)"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


# ---------------------------------------------------------------- Botanical Knowledge Base
BOTANICAL_FAMILY_PROFILES = {
    "lamiaceae": {
        "family_common": "Mint & Sage Family",
        "medicinal": [
            {"title": "Antiseptic & Digestive Soothing", "text": "Rich in therapeutic volatile oils (menthol, rosmarinic acid, thymol) widely used to relieve indigestion, reduce inflammation, and soothe tension headaches."},
            {"title": "Antioxidant & Respiratory Relief", "text": "Traditional steam inhalations and herbal infusions help open nasal airways, ease throat irritation, and supply potent antioxidant polyphenols."}
        ],
        "culinary": [
            {"title": "Culinary & Aromatic Seasoning", "text": "Renowned staple of global gastronomy; freshly picked leaves impart fragrant notes to teas, sauces, salads, pestos, marinades, and beverages."},
            {"title": "Herbal Teas & Infusions", "text": "Leaves dry exceptionally well and make soothing caffeine-free herbal teas celebrated for digestive relaxation."}
        ],
        "domestic": [
            {"title": "Natural Insect & Pest Deterrent", "text": "Aromatic terpenes naturally repel mosquitoes, ants, and garden flies while enticing beneficial pollinators such as bees and butterflies."},
            {"title": "Indoor Air Refreshment", "text": "Emits natural uplifting aromas and helps improve living room air quality."}
        ],
        "care": [
            {"title": "Light & Sunlight", "text": "Prefers bright sunlight (6+ hours of direct or filtered daylight daily)."},
            {"title": "Watering & Soil", "text": "Keep soil evenly moist but well-draining; allow the top inch of soil to dry out between waterings to prevent root rot."}
        ],
        "cautions": [
            {"title": "Essential Oil Concentration", "text": "Pure concentrated essential oils should never be swallowed undiluted; keep away from infants and domestic pets."}
        ]
    },
    "meliaceae": {
        "family_common": "Neem & Mahogany Family",
        "medicinal": [
            {"title": "Antimicrobial & Skin Purifying", "text": "Celebrated in traditional Ayurveda for formidable antibacterial, antifungal, and antiviral qualities that cleanse the skin and promote tissue repair."},
            {"title": "Immune Defense & Blood Detoxification", "text": "Traditional decoctions are valued for systemic purification, blood cleansing, and natural oral periodontal care."}
        ],
        "culinary": [
            {"title": "Traditional Bitter Tonics", "text": "In select regional cultures, tender young leaves and flower buds are gently cooked in bitter broths or therapeutic festival recipes for digestive wellness."}
        ],
        "domestic": [
            {"title": "Natural Organic Pest Control (Azadirachtin)", "text": "Leaves and seed extracts act as the benchmark organic pesticide, disrupting insect breeding cycles without synthetic chemicals."},
            {"title": "Shade & Microclimate Cooling", "text": "Forms an expansive evergreen canopy providing substantial thermal cooling and filtering airborne pollutants."}
        ],
        "care": [
            {"title": "Growing Preferences", "text": "Prefers hot, sunny climates and free-draining sandy or loamy soils. Highly drought-tolerant once established."}
        ],
        "cautions": [
            {"title": "Dosage & Pregnancy", "text": "Concentrated internal consumption is not advised during pregnancy or for small children."}
        ]
    },
    "moraceae": {
        "family_common": "Fig & Mulberry Family",
        "medicinal": [
            {"title": "Cardiovascular & Metabolic Support", "text": "Foliage and bark extracts are traditionally investigated for regulating blood sugar levels and providing natural flavonoids."},
            {"title": "Skin & Wound Conditioning", "text": "Poultices prepared from mature leaves have traditional historical use for soothing localized skin swellings."}
        ],
        "culinary": [
            {"title": "Nutritious Fruits & Leaf Wraps", "text": "Includes premier edible species (figs, mulberries, breadfruit). Fig leaves are often infused to impart rich coconut-vanilla aromas in culinary syrups and steamed dishes."}
        ],
        "domestic": [
            {"title": "Premier Indoor Air Purification", "text": "Broad glossy leaves excel at absorbing airborne volatile pollutants, dust particles, and synthetic toxins according to indoor air studies."},
            {"title": "Biophilic Architectural Greenery", "text": "Stately foliage elevates living environments, lowering ambient cortisol levels and improving interior acoustics."}
        ],
        "care": [
            {"title": "Indoor Plant Care", "text": "Thrives in bright indirect light. Clean broad leaves periodically with a soft damp cloth to optimize photosynthetic efficiency."}
        ],
        "cautions": [
            {"title": "Milky Latex Sap Caution", "text": "Ficus sap contains a milky latex that can cause mild dermatological irritation or tummy upset in pets if chewed."}
        ]
    },
    "araceae": {
        "family_common": "Aroid & Philodendron Family",
        "medicinal": [
            {"title": "Traditional Poultice Applications", "text": "Select genera have historical ethnobotanical uses for topical swelling relief after careful preparation by trained healers."}
        ],
        "culinary": [
            {"title": "Important Tubers (Taro/Cocoyam)", "text": "Roots of specific aroids (like taro) are major world starch staples, though they must always be thoroughly cooked before eating."}
        ],
        "domestic": [
            {"title": "Elite Air Filtering Capacity", "text": "Ranked among the most powerful indoor air-cleansing botanicals, efficiently filtering benzene, formaldehyde, and airborne impurities."},
            {"title": "Iconic Botanical Interior Design", "text": "Lush tropical foliage (Monstera, Pothos, Aglaonema) transforms living spaces into tranquil natural sanctuaries."}
        ],
        "care": [
            {"title": "Care & Light", "text": "Prefers medium to bright indirect light and moderately humid air. Allow soil to dry halfway down before watering."}
        ],
        "cautions": [
            {"title": "Calcium Oxalate Crystals (Pet Toxicity)", "text": "Leaves contain microscopic insoluble raphide crystals. Chewing causes intense oral stinging. Keep strictly away from curious cats and dogs."}
        ]
    },
    "rutaceae": {
        "family_common": "Citrus & Rue Family",
        "medicinal": [
            {"title": "Immune & Cellular Rejuvenation", "text": "Packed with vitamin C precursors, bioflavonoids, and limonoids that combat oxidative stress and reinforce cellular immunity."},
            {"title": "Digestive & Calming Properties", "text": "Aromatic citrus leaf teas assist healthy digestion, ease nausea, and provide gentle uplifting aromatherapeutic calm."}
        ],
        "culinary": [
            {"title": "Gourmet Fragrance & Zest", "text": "Leaves from species like curry tree, kaffir lime, and orange impart vibrant essential citrus oils to curries, soups, and marinades."}
        ],
        "domestic": [
            {"title": "Uplifting Fragrance & Antimicrobial Room Mist", "text": "Essential citrus oils purify living quarters with fresh zesty notes and natural microbial deterrent properties."}
        ],
        "care": [
            {"title": "Sunny Windows & Moisture", "text": "Requires ample sunlight (at least 6-8 hours daily). Use slightly acidic, well-draining soil and feed regularly during spring and summer."}
        ],
        "cautions": [
            {"title": "Phototoxicity", "text": "Contact with raw sap or oils followed by intense direct sunlight can occasionally trigger mild sun-sensitization."}
        ]
    },
    "fabaceae": {
        "family_common": "Legume & Acacia Family",
        "medicinal": [
            {"title": "Anti-inflammatory & Vascular Tonics", "text": "Many legume species feature rich concentrations of flavonoids, saponins, and proanthocyanidins supporting healthy vascular elasticity."},
            {"title": "Traditional Respiratory Soothers", "text": "Licorice and related botanical leaves are historically used to soothe inflamed bronchial passages."}
        ],
        "culinary": [
            {"title": "Vital Protein & Nutrient Source", "text": "World's foundational source of plant protein, dietary fiber, and healthy minerals via beans, peas, and edible pods."}
        ],
        "domestic": [
            {"title": "Natural Soil Nitrogen Enrichment", "text": "Symbiotic root nodules fix atmospheric nitrogen directly into the earth, enriching surrounding soil and rejuvenating garden beds."},
            {"title": "Wildlife & Pollinator Magnet", "text": "Fragrant pea-shaped blossoms supply rich nectar to native pollinators and beneficial garden insects."}
        ],
        "care": [
            {"title": "Soil & Light", "text": "Prefers well-aerated, loamy soils and direct open sunlight. Extremely resilient once root system establishes."}
        ],
        "cautions": [
            {"title": "Raw Foliage Caution", "text": "Certain wild legume varieties possess protective lectins or tannins; avoid eating raw unless definitively identified as an edible cultivar."}
        ]
    },
    "rosaceae": {
        "family_common": "Rose & Apple Family",
        "medicinal": [
            {"title": "Astringent & Anti-inflammatory Action", "text": "Leaves contain gentle tannins and polyphenols traditionally steeped to relieve mild sore throats, gum irritation, and superficial skin blemishes."},
            {"title": "Cellular Vitamin & Antioxidant Boost", "text": "Allied with vitamin-dense fruit and rose hips that enhance microvascular resilience and skin elasticity."}
        ],
        "culinary": [
            {"title": "Herbal Teas & Flavorings", "text": "Young leaves (such as blackberry, raspberry, or strawberry leaf) make mild, mineral-rich herbal teas with pleasant green tea-like notes."},
            {"title": "World-Class Fruits", "text": "Family includes apples, cherries, peaches, plums, and pears, celebrating natural sweetness and pectin fiber."}
        ],
        "domestic": [
            {"title": "Iconic Garden Elegance & Fragrance", "text": "Unrivaled ornamental landscaping appeal, offering romantic garden scents and supporting wild bird populations with autumn hips."}
        ],
        "care": [
            {"title": "Sun & Pruning", "text": "Requires full sunlight and fertile, moist, well-drained soil. Annual pruning encourages strong new leaf growth and vibrant flowering."}
        ],
        "cautions": [
            {"title": "Cyanogenic Glycosides in Seeds/Pits", "text": "While leaves and fruit flesh are generally safe, internal seeds and pits of stone fruits contain amygdalin and should never be chewed."}
        ]
    },
    "asphodelaceae": {
        "family_common": "Aloe & Haworthia Family",
        "medicinal": [
            {"title": "Topical Burn & Skin Healing", "text": "Inner leaf gel is world-renowned for acemannan polysaccharides that dramatically speed up thermal burn recovery, sun relief, and deep epidermal hydration."},
            {"title": "Soothing Anti-inflammatory Gel", "text": "Cools minor cuts, razor burn, insect bites, and dry dermatitis with immediate calming relief."}
        ],
        "culinary": [
            {"title": "Hydrating Health Drinks", "text": "Purified inner fillet gel is incorporated into refreshing wellness drinks and smoothies for digestive and gut comfort."}
        ],
        "domestic": [
            {"title": "Low-Maintenance Living Decor", "text": "Resilient succulent foliage thrives in modern interiors, requiring very little water while releasing night-time oxygen via CAM photosynthesis."}
        ],
        "care": [
            {"title": "Water Sparingly", "text": "Requires bright filtered sunlight and cactus/succulent gritty soil. Water deeply only when the pot is bone dry."}
        ],
        "cautions": [
            {"title": "Yellow Latex Layer (Aloin)", "text": "The bitter yellowish sap just beneath the green skin is a strong purgative laxative. Do not ingest unrefined outer skin."}
        ]
    },
    "malvaceae": {
        "family_common": "Hibiscus & Mallow Family",
        "medicinal": [
            {"title": "Demulcent & Soothing Mucilage", "text": "Leaves and calyces are exceptionally rich in natural plant mucilage that coats and soothes scratchy throats, coughs, and irritated gastric linings."},
            {"title": "Cardiovascular Blood Pressure Support", "text": "Hibiscus teas are scientifically proven to assist healthy cardiovascular circulation and mild systolic pressure moderation."}
        ],
        "culinary": [
            {"title": "Ruby Herbal Teas & Tangy Delicacies", "text": "Brewed worldwide into tart, refreshing iced teas (karkadeh, agua de jamaica) rich in anthocyanins and organic fruit acids."},
            {"title": "Nutritious Greens (Okra/Mallow)", "text": "Young leaves are tender, mild, and frequently prepared as nourishing cooked greens in Mediterranean and African cuisines."}
        ],
        "domestic": [
            {"title": "Showy Ornamental Blossoms & Hair Care", "text": "Petals and leaf extracts are traditionally blended into natural botanical shampoos to foster hair shine and scalp health."}
        ],
        "care": [
            {"title": "Warmth & Feeding", "text": "Thrives in warm, sunny spots with rich compost. Keep consistently moist during the active growing season."}
        ],
        "cautions": [
            {"title": "Mild Diuretic Effect", "text": "Large quantities of tart hibiscus tea possess mild diuretic properties; consume in moderation."}
        ]
    },
    "myrtaceae": {
        "family_common": "Myrtle & Eucalyptus Family",
        "medicinal": [
            {"title": "Potent Decongestant (Cineole)", "text": "Leaves contain high levels of eucalyptol (1,8-cineole), an active compound renowned for clearing respiratory congestion and calming bronchial spasms."},
            {"title": "Antiseptic & Topical Soothing", "text": "Natural antibacterial properties make leaf extracts standard ingredients in antiseptic washes, dental rinses, and therapeutic chest salves."}
        ],
        "culinary": [
            {"title": "Aromatic Spices & Teas", "text": "Allied with allspice, cloves, and lemon myrtle, providing intense aromatic culinary warmth and savory seasoning."},
            {"title": "Delicious Tropical Fruits", "text": "Includes guava and feijoa, providing remarkable doses of dietary vitamin C and dietary fiber."}
        ],
        "domestic": [
            {"title": "Aromatherapeutic Shower & Room Bundles", "text": "Hanging fresh leaf stems in hot showers releases natural therapeutic vapors that refresh the spirit and deter indoor insects."}
        ],
        "care": [
            {"title": "Full Sun & Airflow", "text": "Requires abundant direct sun and good airflow. Tolerates dry periods well once roots have extended."}
        ],
        "cautions": [
            {"title": "Essential Oil Toxicity to Pets", "text": "Eucalyptus and tea tree oils are toxic to dogs and cats if ingested or absorbed on their fur in pure forms."}
        ]
    },
    "asteraceae": {
        "family_common": "Daisy & Sunflower Family",
        "medicinal": [
            {"title": "Anti-inflammatory & Calmative", "text": "Species like chamomile, calendula, and echinacea contain sesquiterpene lactones that promote peaceful sleep, soothe skin, and stimulate immunity."},
            {"title": "Digestive Bitter Stimulation", "text": "Mild bitter compounds in dandelion and artichoke foliage stimulate liver bile flow and optimize digestive health."}
        ],
        "culinary": [
            {"title": "Nutritious Salad Greens & Teas", "text": "Source of classic salad botanicals (lettuce, chicory, endive, tarragon) celebrated for crisp texture and micronutrients."}
        ],
        "domestic": [
            {"title": "Companion Planting & Pollinators", "text": "Essential garden allies (marigolds, sunflowers) that deter nematodes in soil while feeding hundreds of bumblebees and butterflies."}
        ],
        "care": [
            {"title": "Sunlight & Drainage", "text": "Loves full sunlight and light, well-draining garden soil. Deadhead spent blossoms to spur continuous fresh foliage."}
        ],
        "cautions": [
            {"title": "Ragweed & Daisy Allergies", "text": "Individuals sensitive to ragweed may experience mild contact dermatitis or hayfever symptoms around certain composite blooms."}
        ]
    },
    "crassulaceae": {
        "family_common": "Stonecrop & Jade Family",
        "medicinal": [
            {"title": "Cooling Poultice & Hydration", "text": "Fleshy succulent leaves are crushed in folk medicine to cool minor burns, insect bites, and localized inflammatory skin flare-ups."}
        ],
        "culinary": [
            {"title": "Mild Edible Succulents", "text": "Species such as Sedum and purslane are occasionally enjoyed raw in salads for a refreshing, slightly sour mineral crunch."}
        ],
        "domestic": [
            {"title": "Living Indoor Sculptures", "text": "Architectural, geometric fleshy leaves store water, thriving on window sills and demanding minimal watering maintenance."},
            {"title": "Nighttime Air Refreshment", "text": "Utilizes Crassulacean Acid Metabolism (CAM) to open stomata and release oxygen during the night."}
        ],
        "care": [
            {"title": "Dry & Bright", "text": "Requires gritty, well-draining cactus mix. Water only when the soil is completely dry; overwatering causes leaf drop."}
        ],
        "cautions": [
            {"title": "Pet Safety Note", "text": "Common jade plants (Crassula ovata) and Kalanchoe species are mildly toxic to cats and dogs if ingested."}
        ]
    }
}

GENERIC_BOTANICAL_PROFILE = {
    "medicinal": [
        {"title": "Natural Botanical Antioxidants", "text": "Leaf tissue contains natural chlorophyll, flavonoids, and plant polyphenols that assist cellular resilience and combat oxidative stress."},
        {"title": "Aromatherapeutic & Wellness Value", "text": "The natural biophilic aroma and visual presence of living foliage has been shown to reduce heart rate, lower stress, and enhance mental focus."}
    ],
    "culinary": [
        {"title": "Herbal & Dietary Verification", "text": "Leaves of confirmed edible varieties are widely infused in herbal teas, delicate culinary wraps, or aromatic broths. Always confirm culinary safety before tasting."}
    ],
    "domestic": [
        {"title": "Natural Air Purification & Humidity", "text": "Performs active daytime photosynthesis, capturing carbon dioxide, releasing clean oxygen, and naturally humidifying indoor spaces through transpiration."},
        {"title": "Biophilic Decor & Stress Reduction", "text": "Incorporating living green plants into study and living quarters creates a serene, grounded atmosphere that enhances daily mood."}
    ],
    "care": [
        {"title": "Sunlight & Light Exposure", "text": "Most leafy varieties flourish in bright, filtered daylight. Avoid harsh scorching midday rays that might bleach leaf margins."},
        {"title": "Watering & Soil Drainage", "text": "Use a pot with drainage holes and aerated, well-draining soil. Check soil moisture with your finger before each watering."}
    ],
    "cautions": [
        {"title": "Safety & Botanical Advisory", "text": "Do not consume or chew wild plant leaves unless verified by a certified botanist or food safety specialist. Keep unknown houseplants away from pets."}
    ]
}


# ---------------------------------------------------------------- images
def prepare_image(raw: bytes):
    """Validate the upload and return a resized JPEG, or None if not an image."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError):
        return None
    img = img.convert("RGB")
    img.thumbnail((1280, 1280))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


# ---------------------------------------------------------------- Pl@ntNet
def plantnet_identify(jpeg: bytes):
    r = requests.post(
        "https://my-api.plantnet.org/v2/identify/all",
        params={
            "api-key": PLANTNET_KEY,
            "lang": "en",
            "nb-results": 5,
            "include-related-images": "true",
        },
        files=[("images", ("leaf.jpg", jpeg, "image/jpeg"))],
        data={"organs": "leaf"},
        timeout=40,
    )
    if r.status_code == 404:  # "Species not found" -> nothing plant-like
        return []
    r.raise_for_status()
    return r.json().get("results", [])


# ---------------------------------------------------------------- Google Lens
def google_lens_matches(jpeg: bytes):
    """Optional. Google has no official Lens API, so SerpApi's Lens engine is used.
    Lens needs a public image URL, so the leaf is first hosted on imgbb for 10 min."""
    if not (SERPAPI_KEY and IMGBB_KEY):
        return []
    try:
        up = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_KEY, "expiration": 600},
            data={"image": base64.b64encode(jpeg).decode()},
            timeout=40,
        )
        up.raise_for_status()
        image_url = up.json()["data"]["url"]
        lens = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_lens", "url": image_url, "api_key": SERPAPI_KEY},
            timeout=60,
        )
        lens.raise_for_status()
        matches = lens.json().get("visual_matches", [])[:5]
        return [
            {"title": m.get("title"), "source": m.get("source"), "link": m.get("link")}
            for m in matches
            if m.get("title") and m.get("link")
        ]
    except (requests.RequestException, KeyError, ValueError):
        return []


# ---------------------------------------------------------------- Wikipedia Knowledge Engine
HEADING = re.compile(r"^(={2,4})\s*(.+?)\s*\1\s*$", re.M)
MEDICINAL_WORDS = ("medic", "health", "cure", "remedy", "therap", "ayurved", "herbal",
                   "ethnobot", "pharmac", "healing", "antiseptic", "antioxidant",
                   "anti-inflamm", "disease", "fever", "wound", "skin")
CULINARY_WORDS = ("culinary", "cook", "food", "edible", "fruit", "vegetable", "spice",
                  "herb", "flavor", "flavour", "salad", "tea", "beverage", "drink",
                  "cuisine", "nutrit", "diet", "dish")
DOMESTIC_WORDS = ("use", "commercial", "economic", "wood", "timber", "fiber", "fibre",
                  "latex", "resin", "oil", "essential oil", "perfume", "fragrance",
                  "dye", "soap", "cosmetic", "ornamental", "cultivat", "garden",
                  "landscape", "indoor", "air", "pest", "repellent", "companion",
                  "material", "horticultur", "gum")
WARN_WORDS = ("toxic", "poison", "caution", "safety", "adverse", "allerg", "hazard", "oxalate", "irrit")
DISTRIBUTION_WORDS = ("distribution", "habitat", "range", "native range", "origin", "ecology", "geograph")


# ---------------------------------------------------------------- Botanical Geographic Distribution Engine
BOTANICAL_DISTRIBUTION_DATABASE = {
    "bidens": {
        "native_range": "Tropical & Subtropical Americas",
        "climate": "Pantropical, Subtropical & Warm Temperate (USDA 8–11)",
        "habitat": "Open sunny pastures, agricultural field margins, roadsides, disturbed soils, coastal riverbanks",
        "summary": "Originally indigenous to the tropical and subtropical Americas, Bidens pilosa is now widely naturalized across warm temperate and pantropical regions worldwide.",
        "center": [15.0, 10.0],
        "zoom": 2,
        "locations": [
            {"name": "Tropical Americas (Caribbean & Central America)", "status": "Native Range", "lat": 18.5, "lng": -72.0, "radius": 2200000, "description": "Ancestral evolutionary homeland; thrives in sunny clearings, valleys and agricultural edges."},
            {"name": "Indian Subcontinent (India & Sri Lanka)", "status": "Naturalized", "lat": 20.59, "lng": 78.96, "radius": 1500000, "description": "Widely naturalized across the plains, Western Ghats, and agricultural homesteads."},
            {"name": "Sub-Saharan Africa", "status": "Naturalized", "lat": -1.2, "lng": 28.0, "radius": 2500000, "description": "Prevalent throughout eastern, central, and southern African savanna zones."},
            {"name": "Southeast Asia & Pacific", "status": "Naturalized", "lat": 7.0, "lng": 115.0, "radius": 2000000, "description": "Abundant across coastal margins, roadsides, and tropical riverbeds."}
        ]
    },
    "ocimum": {
        "native_range": "Indian Subcontinent & Southeast Asia",
        "climate": "Tropical & Subtropical (Warm, Frost-sensitive, USDA 10–12)",
        "habitat": "Homestead gardens, temple courtyards, tropical forest fringes, moist fertile soils",
        "summary": "Native to the Indian Subcontinent and Southeast Asia; sacred in Ayurveda for thousands of years and cultivated globally across warm temperate zones.",
        "center": [20.0, 78.0],
        "zoom": 3,
        "locations": [
            {"name": "Indian Subcontinent (India, Sri Lanka, Nepal)", "status": "Native Range", "lat": 20.59, "lng": 78.96, "radius": 1700000, "description": "Sacred indigenous origin; thrives in rich fertile soils with bright sunlight."},
            {"name": "Southeast Asia (Thailand, Malaysia, Indonesia)", "status": "Native Range", "lat": 5.5, "lng": 105.0, "radius": 1800000, "description": "Native wild and cultivated populations in moist tropical forest fringes."},
            {"name": "Mediterranean Basin & Southern Europe", "status": "Cultivated", "lat": 38.0, "lng": 15.0, "radius": 1400000, "description": "Cultivated widely as a culinary and aromatic staple since ancient times."},
            {"name": "Tropical Americas", "status": "Naturalized", "lat": 10.0, "lng": -75.0, "radius": 1800000, "description": "Grown in home gardens and naturalized across Caribbean and Latin American regions."}
        ]
    },
    "azadirachta": {
        "native_range": "Indian Subcontinent & Indochina",
        "climate": "Tropical & Subtropical Semi-Arid (High Heat & Drought Hardy, USDA 10–12)",
        "habitat": "Dry deciduous forests, thorny scrublands, roadside avenues, sandy well-draining soils",
        "summary": "Native to the dry deciduous woodlands of India and Myanmar. Revered as the 'Village Pharmacy', it is planted across arid zones of Africa, the Caribbean, and Australia for reforestation and organic pest defense.",
        "center": [18.0, 50.0],
        "zoom": 3,
        "locations": [
            {"name": "Indian Subcontinent (India, Bangladesh, Myanmar)", "status": "Native Range", "lat": 21.0, "lng": 79.0, "radius": 1700000, "description": "Native heartland; flourishes across the Deccan Plateau, Indo-Gangetic plains, and dry forests."},
            {"name": "Sub-Saharan & Sahelian Africa", "status": "Cultivated & Naturalized", "lat": 12.0, "lng": 15.0, "radius": 2400000, "description": "Key reforestation tree across Senegal, Mali, Nigeria, and Sudan against desertification."},
            {"name": "Caribbean & Central America", "status": "Cultivated", "lat": 17.0, "lng": -68.0, "radius": 1200000, "description": "Planted in homesteads and coastal areas for organic shade and medicinal foliage."},
            {"name": "Northern Australia", "status": "Naturalized", "lat": -18.0, "lng": 135.0, "radius": 1400000, "description": "Thrives in tropical savanna and dry northern pastoral regions."}
        ]
    },
    "ficus": {
        "native_range": "South & Southeast Asia, Pantropical",
        "climate": "Tropical & Subtropical (Warm, Monsoonal, USDA 9–12)",
        "habitat": "Lowland tropical forests, riverbanks, rock crevices, temple shrines, indoor patios",
        "summary": "Native to monsoonal Asia and pantropical rainforests; keystone ecological genus renowned for sacred banyans, peepals, and architectural foliage plants.",
        "center": [15.0, 80.0],
        "zoom": 3,
        "locations": [
            {"name": "Indian Subcontinent (India, Nepal, Sri Lanka)", "status": "Native Range", "lat": 21.0, "lng": 78.5, "radius": 1800000, "description": "Native home of sacred Peepal (Ficus religiosa) and legendary Banyan (Ficus benghalensis)."},
            {"name": "Southeast Asia (Northeast India, Malaysia, Indonesia)", "status": "Native Range", "lat": 8.0, "lng": 105.0, "radius": 2000000, "description": "Native rainforest cradle of Rubber Fig (Ficus elastica) and strangler figs."},
            {"name": "Mediterranean Basin & Middle East", "status": "Native & Cultivated", "lat": 35.0, "lng": 25.0, "radius": 1500000, "description": "Homeland of Common Edible Fig (Ficus carica) cultivated since antiquity."}
        ]
    },
    "monstera": {
        "native_range": "Tropical Rainforests of Central America & Southern Mexico",
        "climate": "Tropical Rainforest & Humid Subtropical (USDA 10–12)",
        "habitat": "Moist tropical rainforest understory, climbing tree trunks as an epiphyte",
        "summary": "Native to the dense tropical rainforests of Southern Mexico, Guatemala, Costa Rica, and Panama; iconic global architectural houseplant.",
        "center": [15.0, -88.0],
        "zoom": 4,
        "locations": [
            {"name": "Mesoamerica (Southern Mexico, Guatemala, Belize)", "status": "Native Range", "lat": 16.5, "lng": -90.5, "radius": 1100000, "description": "Native evolutionary habitat, climbing up tall forest trunks towards filtered canopy light."},
            {"name": "Central America (Costa Rica, Panama)", "status": "Native Range", "lat": 9.5, "lng": -83.5, "radius": 800000, "description": "Native wet premontane and cloud forests with year-round high humidity."},
            {"name": "Global Indoor Horticulture", "status": "Cultivated", "lat": 20.0, "lng": 78.0, "radius": 2200000, "description": "Celebrated worldwide in biophilic interior spaces and botanical conservatories."}
        ]
    },
    "aloe": {
        "native_range": "Arabian Peninsula (Oman & Yemen)",
        "climate": "Arid, Semi-Arid & Warm Mediterranean (Frost Sensitive, USDA 9–11)",
        "habitat": "Rocky arid hillsides, well-draining gravel soils, desert scrublands",
        "summary": "Indigenous to the arid mountain cliffs of the southern Arabian Peninsula; widely naturalized across North Africa, the Mediterranean Basin, India, and the Americas.",
        "center": [20.0, 45.0],
        "zoom": 3,
        "locations": [
            {"name": "Arabian Peninsula (Oman & Yemen)", "status": "Native Range", "lat": 17.5, "lng": 54.0, "radius": 900000, "description": "Ancestral native habitat in arid limestone ravines and mountain plateau slopes."},
            {"name": "North Africa & Mediterranean", "status": "Naturalized", "lat": 32.0, "lng": 15.0, "radius": 1800000, "description": "Naturalized along coastal scrub and rocky slopes for over two millennia."},
            {"name": "Indian Subcontinent (Dry Zones)", "status": "Naturalized & Cultivated", "lat": 24.0, "lng": 73.0, "radius": 1300000, "description": "Cultivated across Rajasthan, Gujarat, and Tamil Nadu for Ayurvedic skincare."},
            {"name": "Southwestern US & Mexico", "status": "Cultivated & Naturalized", "lat": 25.0, "lng": -102.0, "radius": 1600000, "description": "Flourishes in arid and semi-arid desert landscapes and sunny patios."}
        ]
    },
    "mangifera": {
        "native_range": "South Asia (India, Bangladesh, Myanmar)",
        "climate": "Tropical & Subtropical with Dry Winter/Spring (USDA 10–12)",
        "habitat": "Lowland tropical wet and dry deciduous forests, alluvial river plains",
        "summary": "Native to the fertile river valleys and subtropical forests of India and Myanmar. Cultivated for over 4,000 years and now grown across all warm tropical regions of the world.",
        "center": [20.0, 80.0],
        "zoom": 3,
        "locations": [
            {"name": "Indian Subcontinent (India & Bangladesh)", "status": "Native Range", "lat": 22.0, "lng": 80.0, "radius": 1700000, "description": "Native cradle with unparalleled genetic diversity; India produces nearly half the world's mangoes."},
            {"name": "Southeast Asia (Myanmar, Thailand, Vietnam)", "status": "Native Range", "lat": 15.0, "lng": 100.0, "radius": 1500000, "description": "Indigenous in monsoonal forests and river floodplains."},
            {"name": "Tropical Americas (Brazil, Mexico, Caribbean)", "status": "Cultivated", "lat": -8.0, "lng": -50.0, "radius": 2200000, "description": "Major commercial cultivation zone introduced during early maritime trade."}
        ]
    },
    "hibiscus": {
        "native_range": "Tropical East & Southeast Asia",
        "climate": "Tropical & Subtropical (Frost Sensitive, USDA 9–11)",
        "habitat": "Tropical coastlines, sunny thickets, humid warm valleys",
        "summary": "Native to tropical Asia and the Pacific; widely celebrated as the queen of tropical flowers across South Asia, the Caribbean, and Hawaii.",
        "center": [15.0, 105.0],
        "zoom": 3,
        "locations": [
            {"name": "Tropical East & Southeast Asia", "status": "Native Range", "lat": 18.0, "lng": 108.0, "radius": 1800000, "description": "Native home in sunny coastal valleys and tropical borderlands."},
            {"name": "Indian Subcontinent", "status": "Cultivated & Naturalized", "lat": 20.0, "lng": 78.0, "radius": 1600000, "description": "Ubiquitous ornamental and Ayurvedic sacred flower grown in every home garden."},
            {"name": "Pacific Islands & Hawaii", "status": "Cultivated", "lat": 20.0, "lng": -157.0, "radius": 1000000, "description": "State flower and cultural emblem thriving in volcanic tropical soils."}
        ]
    },
    "moringa": {
        "native_range": "Sub-Himalayan Tracts of Northwestern India",
        "climate": "Tropical & Subtropical Semi-Arid (Drought Hardy, USDA 9–11)",
        "habitat": "Sandy floodplains, dry riverbeds, well-draining coastal plains",
        "summary": "Native to the sub-Himalayan tracts of northern India; widely cultivated across tropical Asia, Africa, and Central America as an extraordinary nutrient-dense superfood tree.",
        "center": [25.0, 78.0],
        "zoom": 3,
        "locations": [
            {"name": "Northwestern India (Sub-Himalayan Plains)", "status": "Native Range", "lat": 28.0, "lng": 77.0, "radius": 1200000, "description": "Native indigenous region; deeply embedded in traditional Indian horticulture and gastronomy."},
            {"name": "South India & Sri Lanka", "status": "Cultivated", "lat": 12.0, "lng": 78.0, "radius": 1000000, "description": "Staple vegetable crop cultivated for drumsticks and tender protein-rich leaves."},
            {"name": "Tropical Africa (Kenya, Ethiopia, Nigeria)", "status": "Naturalized & Cultivated", "lat": 8.0, "lng": 30.0, "radius": 2200000, "description": "Championed in dryland farming for food security, water purification, and nutrition."}
        ]
    },
    "murraya": {
        "native_range": "Indian Subcontinent & Sri Lanka",
        "climate": "Tropical & Subtropical (Warm, Moist, USDA 9–12)",
        "habitat": "Moist deciduous forests, foothills, homestead gardens",
        "summary": "Native to the Indian subcontinent and Sri Lanka. Treasured across South Asian cuisine for intense culinary fragrance and digestive benefits.",
        "center": [18.0, 79.0],
        "zoom": 4,
        "locations": [
            {"name": "India (Western Ghats & Deccan)", "status": "Native Range", "lat": 18.0, "lng": 78.0, "radius": 1600000, "description": "Native habitat in deciduous forest understories and home gardens throughout the subcontinent."},
            {"name": "Sri Lanka", "status": "Native Range", "lat": 7.8, "lng": 80.7, "radius": 500000, "description": "Wild and cultivated indigenous shrub essential to island cuisine."},
            {"name": "Southeast Asia (Malaysia & Singapore)", "status": "Cultivated", "lat": 3.5, "lng": 102.0, "radius": 800000, "description": "Cultivated by diaspora communities in tropical kitchen gardens."}
        ]
    },
    "mentha": {
        "native_range": "Temperate Eurasia & North America",
        "climate": "Cool Temperate to Warm Subtropical (USDA 3–9)",
        "habitat": "Moist stream banks, wet meadows, damp forest margins",
        "summary": "Native to temperate wetlands across Europe, Asia, and North America, with unmatched ability to spread via underground stolons in moist soils.",
        "center": [45.0, 30.0],
        "zoom": 3,
        "locations": [
            {"name": "Europe & Mediterranean", "status": "Native Range", "lat": 46.0, "lng": 12.0, "radius": 1800000, "description": "Native wetland corridors, damp riverbanks, and alpine meadows."},
            {"name": "Central & South Asia", "status": "Native & Cultivated", "lat": 28.0, "lng": 75.0, "radius": 1700000, "description": "Abundant culinary and commercial cultivation across northern India and Pakistan."},
            {"name": "North America", "status": "Naturalized", "lat": 40.0, "lng": -95.0, "radius": 2200000, "description": "Naturalized in ditches, wetlands, and gardens from coast to coast."}
        ]
    },
    "citrus": {
        "native_range": "Southeast Asia, South Asia, East Asia & Northern Australia",
        "climate": "Subtropical & Warm Temperate (Frost Sensitive, USDA 9–11)",
        "habitat": "Monsoonal evergreen forests, subtropical foothills, fertile valleys",
        "summary": "Native to the subtropical foothills and monsoonal forests of South and Southeast Asia, now cultivated globally across the Mediterranean, Americas, and Asia.",
        "center": [20.0, 95.0],
        "zoom": 3,
        "locations": [
            {"name": "Southeast Asia & South China", "status": "Native Range", "lat": 20.0, "lng": 105.0, "radius": 1800000, "description": "Evolutionary homeland of primitive citrus ancestors (mandarins, pomelos, citrons)."},
            {"name": "Indian Subcontinent (Northeast Foothills)", "status": "Native Range", "lat": 26.0, "lng": 91.0, "radius": 1200000, "description": "Wild citrus species flourish in Meghalaya and Assam foothills."},
            {"name": "Mediterranean & Southern Europe", "status": "Cultivated", "lat": 38.0, "lng": 15.0, "radius": 1600000, "description": "Legendary citrus groves producing lemons, oranges, and bergamot."},
            {"name": "Americas (Florida, California, Brazil)", "status": "Cultivated", "lat": 28.0, "lng": -82.0, "radius": 1800000, "description": "Vast commercial citrus orchards introduced in colonial times."}
        ]
    },
    "sansevieria": {
        "native_range": "Tropical West Africa (Nigeria to Congo)",
        "climate": "Tropical Dry & Semi-Arid (High Drought Tolerance, USDA 10–12)",
        "habitat": "Dry open woodlands, rocky savannas, scrub thickets",
        "summary": "Native to tropical West Africa from Nigeria east to the Congo basin. Renowned as an indestructible houseplant with NASA-certified air purifying power.",
        "center": [7.0, 10.0],
        "zoom": 4,
        "locations": [
            {"name": "Tropical West Africa (Nigeria, Cameroon, Congo)", "status": "Native Range", "lat": 7.0, "lng": 12.0, "radius": 1600000, "description": "Native forest floor succulent adapted to surviving extended dry seasons."},
            {"name": "Pantropical Indoors & Landscape Gardens", "status": "Cultivated", "lat": 20.0, "lng": 78.0, "radius": 2400000, "description": "Grown globally in interior offices, apartments, and tropical landscape beds."}
        ]
    },
    "epipremnum": {
        "native_range": "Mo'orea (Society Islands, French Polynesia)",
        "climate": "Humid Tropical & Subtropical (USDA 10–12)",
        "habitat": "Tropical rainforest canopy, climbing tree trunks via aerial rootlets",
        "summary": "Native originally to the volcanic island of Mo'orea in French Polynesia; now naturalized in pantropical rainforests and cultivated in millions of homes worldwide.",
        "center": [-17.5, -149.8],
        "zoom": 3,
        "locations": [
            {"name": "Society Islands (French Polynesia - Mo'orea)", "status": "Native Range", "lat": -17.53, "lng": -149.83, "radius": 600000, "description": "Native endemic island cradle where giant mature split-leaf forms climb rainforest trees."},
            {"name": "South & Southeast Asia", "status": "Naturalized & Cultivated", "lat": 18.0, "lng": 85.0, "radius": 2200000, "description": "Beloved as the household 'Money Plant', flourishing in water jars and gardens."},
            {"name": "Tropical Americas & Caribbean", "status": "Naturalized", "lat": 15.0, "lng": -75.0, "radius": 2000000, "description": "Climbs wild trees throughout Caribbean islands and Florida hammocks."}
        ]
    },
    "rosa": {
        "native_range": "Temperate Asia, Europe & North America",
        "climate": "Temperate & Warm Subtropical (USDA 4–9)",
        "habitat": "Sunny hedgerows, open scrublands, fertile slopes",
        "summary": "Native predominantly to temperate Asia, with smaller native ranges in Europe, North America, and Northwestern Africa. Cultivated globally for ornamental flowers and fragrance.",
        "center": [35.0, 60.0],
        "zoom": 3,
        "locations": [
            {"name": "East & Central Asia (China & Persia)", "status": "Native Range", "lat": 32.0, "lng": 85.0, "radius": 2200000, "description": "Ancient diversity heartland of repeat-flowering wild rose ancestors."},
            {"name": "Europe & Mediterranean", "status": "Native Range", "lat": 48.0, "lng": 15.0, "radius": 1600000, "description": "Native dog-roses (Rosa canina) and sweet briar in sunny hillsides and hedgerows."},
            {"name": "North America", "status": "Native Range", "lat": 42.0, "lng": -95.0, "radius": 2000000, "description": "Native prairie and wood roses blooming in temperate grasslands."}
        ]
    },
    # Botanical Family Fallbacks
    "lamiaceae": {
        "native_range": "Mediterranean Basin, Eurasia & Global Subtropics",
        "climate": "Temperate, Mediterranean & Subtropical (USDA 5–11)",
        "habitat": "Sunny rocky hillsides, scrub garrigues, well-draining soils",
        "summary": "The mint and sage family has its primary diversity center in the Mediterranean Basin and Central Asia, with members adapted to sunny, free-draining landscapes across all continents.",
        "center": [35.0, 30.0],
        "zoom": 3,
        "locations": [
            {"name": "Mediterranean Basin (Southern Europe & North Africa)", "status": "Native Center", "lat": 36.0, "lng": 15.0, "radius": 1800000, "description": "Prime evolutionary diversity zone for thyme, oregano, lavender, and rosemary."},
            {"name": "South & East Asia", "status": "Native & Cultivated", "lat": 22.0, "lng": 85.0, "radius": 2000000, "description": "Hub for aromatic Ocimum (tulsi), Perilla, and medicinal mints."},
            {"name": "Americas", "status": "Naturalized & Native", "lat": 20.0, "lng": -90.0, "radius": 2200000, "description": "Extensive presence of native salvias and naturalized culinary herbs."}
        ]
    },
    "moraceae": {
        "native_range": "Pantropical & Subtropical Regions",
        "climate": "Tropical Rainforest & Humid Subtropical (USDA 9–12)",
        "habitat": "Lowland tropical rainforests, river floodplains, monsoonal woodlands",
        "summary": "The fig and mulberry family is predominantly pantropical, with major species diversity centered in tropical Asia, Africa, and the Neotropics.",
        "center": [10.0, 60.0],
        "zoom": 2,
        "locations": [
            {"name": "Indomalayan Realm (South & Southeast Asia)", "status": "Native Diversity Hotspot", "lat": 15.0, "lng": 95.0, "radius": 2400000, "description": "Unrivaled diversity of banyans, sacred peepals, and edible figs."},
            {"name": "Tropical Africa", "status": "Native Range", "lat": 0.0, "lng": 20.0, "radius": 2400000, "description": "Abundant strangler figs and riparian forest canopies."},
            {"name": "Neotropical Americas", "status": "Native Range", "lat": 5.0, "lng": -65.0, "radius": 2400000, "description": "Canopy trees and lianas across the Amazon Basin and Central America."}
        ]
    },
    "araceae": {
        "native_range": "Neotropics & Indomalayan Rainforests",
        "climate": "Humid Tropical & Subtropical Understory (USDA 10–12)",
        "habitat": "Dense rainforest understory, damp ravines, tree trunks as epiphytes",
        "summary": "The arum and philodendron family is concentrated in the humid tropical rainforests of the Americas and Southeast Asia, adapted to filtered light and high humidity.",
        "center": [10.0, -40.0],
        "zoom": 2,
        "locations": [
            {"name": "Neotropical Rainforests (Central & South America)", "status": "Primary Diversity Center", "lat": 8.0, "lng": -70.0, "radius": 2400000, "description": "Epicenter for Monstera, Philodendron, Anthurium, and Syngonium."},
            {"name": "Indomalayan Realm (Southeast Asia & India)", "status": "Native Range", "lat": 12.0, "lng": 100.0, "radius": 2200000, "description": "Homeland of Alocasia, Aglaonema, Epipremnum, and giant Amorphophallus."},
            {"name": "Tropical Africa", "status": "Native Range", "lat": 2.0, "lng": 20.0, "radius": 2000000, "description": "Native Anubias and forest floor wetland aroids."}
        ]
    },
    "meliaceae": {
        "native_range": "Indomalaya, Sub-Saharan Africa & Neotropics",
        "climate": "Tropical & Subtropical (Warm, Drought Tolerant, USDA 10–12)",
        "habitat": "Dry deciduous woodlands, evergreen rainforests, coastal river valleys",
        "summary": "The mahogany family spans the pantropical belt, renowned for valuable hardwoods and resilient medicinal trees like Neem.",
        "center": [15.0, 50.0],
        "zoom": 3,
        "locations": [
            {"name": "South & Southeast Asia", "status": "Native Range", "lat": 18.0, "lng": 80.0, "radius": 2000000, "description": "Native home of Neem, Toona, and Asian mahogany species."},
            {"name": "Tropical Africa & Madagascar", "status": "Native Range", "lat": 0.0, "lng": 25.0, "radius": 2200000, "description": "African mahogany (Khaya) in gallery forests and savanna edges."},
            {"name": "Neotropical Americas", "status": "Native Range", "lat": -5.0, "lng": -60.0, "radius": 2400000, "description": "Native Swietenia (genuine mahogany) in Amazonian and Central American forests."}
        ]
    },
    "asphodelaceae": {
        "native_range": "Southern Africa, Madagascar & Arabian Peninsula",
        "climate": "Arid, Semi-Arid & Mediterranean (USDA 9–11)",
        "habitat": "Rocky slopes, dry scrublands, desert ravines",
        "summary": "Centered in Southern Africa and Madagascar, with arid adaptations such as succulent water-storing leaves.",
        "center": [-25.0, 28.0],
        "zoom": 4,
        "locations": [
            {"name": "Southern Africa (Cape & Karoo)", "status": "Primary Diversity Center", "lat": -30.0, "lng": 25.0, "radius": 1500000, "description": "Richest concentration of Aloe, Haworthia, and Gasteria in rocky gorges."},
            {"name": "Madagascar", "status": "Native Center", "lat": -19.0, "lng": 47.0, "radius": 900000, "description": "Unique endemic tree aloes and desert scrub flora."},
            {"name": "Arabian Peninsula", "status": "Native Range", "lat": 20.0, "lng": 48.0, "radius": 1200000, "description": "Ancestral homeland of Aloe vera in arid limestone mountain ranges."}
        ]
    },
    "rutaceae": {
        "native_range": "Australasia, East Asia & Tropical Regions",
        "climate": "Subtropical & Warm Temperate (USDA 9–11)",
        "habitat": "Subtropical forests, monsoonal hillsides, citrus valleys",
        "summary": "The citrus and rue family is centered in the warm temperate and tropical regions of Australasia and East Asia.",
        "center": [15.0, 100.0],
        "zoom": 3,
        "locations": [
            {"name": "East & Southeast Asia", "status": "Native Diversity Center", "lat": 22.0, "lng": 105.0, "radius": 2000000, "description": "Ancestral origin of wild citrus, Murraya (curry leaf), and Zanthoxylum."},
            {"name": "Australasia", "status": "Native Range", "lat": -25.0, "lng": 135.0, "radius": 2000000, "description": "Native finger limes and aromatic Boronia shrubs."},
            {"name": "Mediterranean Basin", "status": "Cultivated", "lat": 38.0, "lng": 15.0, "radius": 1600000, "description": "Iconic lemon, orange, and olive groves across coastal terraces."}
        ]
    },
    "asteraceae": {
        "native_range": "Cosmopolitan (Global Distribution)",
        "climate": "Temperate, Subtropical & Tropical (USDA 3–11)",
        "habitat": "Sunny grasslands, prairies, roadsides, disturbed soils, mountain meadows",
        "summary": "The daisy and sunflower family is one of the largest plant families on Earth, found on every continent except Antarctica, excelling in open sunny habitats.",
        "center": [20.0, 10.0],
        "zoom": 2,
        "locations": [
            {"name": "Americas (North, Central & South)", "status": "Major Center of Diversity", "lat": 25.0, "lng": -95.0, "radius": 2600000, "description": "Epicenter for sunflowers, Bidens, tagetes, and wild prairies."},
            {"name": "Eurasia & Mediterranean", "status": "Native Range", "lat": 45.0, "lng": 40.0, "radius": 2500000, "description": "Home to wild chamomile, chicory, daisies, and artemisia."},
            {"name": "Southern & Eastern Africa", "status": "Native Range", "lat": -15.0, "lng": 30.0, "radius": 2200000, "description": "High floral endemism across Karoo, fynbos, and montane grasslands."}
        ]
    },
    "fabaceae": {
        "native_range": "Cosmopolitan & Pantropical",
        "climate": "Tropical, Subtropical & Temperate (USDA 3–11)",
        "habitat": "Savannas, woodlands, grasslands, agricultural soils",
        "summary": "The legume family is ubiquitous worldwide, known for nitrogen-fixing root nodules that enrich poor soils.",
        "center": [15.0, 20.0],
        "zoom": 2,
        "locations": [
            {"name": "Tropical Savannas & Woodlands (Africa & Asia)", "status": "Native Diversity Center", "lat": 5.0, "lng": 30.0, "radius": 2400000, "description": "Abundant Acacia, Senegalia, and Tamarindus across sunny landscapes."},
            {"name": "Neotropical Americas", "status": "Native Range", "lat": 0.0, "lng": -60.0, "radius": 2500000, "description": "Great diversity of Inga, Mimosa, and bean crops."},
            {"name": "Temperate Eurasia", "status": "Native Range", "lat": 48.0, "lng": 45.0, "radius": 2200000, "description": "Wild clover, vetch, and medicago enriching pastures."}
        ]
    },
    "default": {
        "native_range": "Tropical, Subtropical & Warm Temperate Zones",
        "climate": "Subtropical to Tropical (USDA 8–11)",
        "habitat": "Fertile soils, forest borders, sun-exposed clearings, cultivated gardens",
        "summary": "Grows primarily in tropical and warm temperate zones with ample daylight and well-draining soil.",
        "center": [18.0, 40.0],
        "zoom": 2,
        "locations": [
            {"name": "South & Southeast Asia", "status": "Cultivated & Native", "lat": 18.0, "lng": 85.0, "radius": 2000000, "description": "Thrives in monsoonal warmth and fertile tropical soils."},
            {"name": "Mediterranean & Southern Europe", "status": "Cultivated", "lat": 38.0, "lng": 15.0, "radius": 1600000, "description": "Adapted to sunny dry summers and mild winters."},
            {"name": "Tropical Americas", "status": "Native & Naturalized", "lat": 10.0, "lng": -75.0, "radius": 2000000, "description": "Flourishes in tropical rainforest margins and garden landscapes."}
        ]
    }
}


def resolve_plant_distribution(scientific_name: str, common_names: list = None, family: str = None, wiki_dist_text: str = ""):
    """Resolve geographic growing range, native habitat, and Leaflet coordinates."""
    common_names = common_names or []
    sci_lower = (scientific_name or "").lower()
    fam_lower = (family or "").lower()
    genus_lower = sci_lower.split()[0] if sci_lower else ""

    matched = None
    # 1. Check exact species or genus
    for key, data in BOTANICAL_DISTRIBUTION_DATABASE.items():
        if key in sci_lower or key == genus_lower:
            matched = data
            break

    # 2. Check family fallback
    if not matched:
        matched = BOTANICAL_DISTRIBUTION_DATABASE.get(fam_lower)

    # 3. Fallback to generic
    if not matched:
        matched = BOTANICAL_DISTRIBUTION_DATABASE["default"]

    dist = {
        "native_range": matched["native_range"],
        "climate": matched["climate"],
        "habitat": matched["habitat"],
        "summary": matched["summary"],
        "center": matched.get("center", [20.0, 20.0]),
        "zoom": matched.get("zoom", 2),
        "locations": list(matched.get("locations", [])),
    }

    if wiki_dist_text and len(wiki_dist_text.strip()) > 25:
        clean_wiki = clip(wiki_dist_text.strip(), 400)
        dist["summary"] = clean_wiki

    return dist


def clip(text: str, limit: int = 650) -> str:
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def fetch_wiki_page(title: str):
    """Fetch Wikipedia extract by title or redirect."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "format": "json", "prop": "extracts",
                    "explaintext": 1, "redirects": 1, "titles": title},
            headers=UA,
            timeout=15,
        )
        r.raise_for_status()
        page = next(iter(r.json()["query"]["pages"].values()))
        if "missing" not in page and page.get("extract"):
            return page.get("title", title), page.get("extract")
    except Exception:
        pass
    return None, None


def search_wiki(query: str):
    """Search Wikipedia if direct title fails."""
    t, text = fetch_wiki_page(query)
    if text:
        return t, text
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "format": "json", "list": "search",
                    "srsearch": query, "srlimit": 2},
            headers=UA,
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("query", {}).get("search", [])
        if results:
            return fetch_wiki_page(results[0]["title"])
    except Exception:
        pass
    return None, None


def parse_hierarchical_sections(text: str):
    """Parse Wikipedia extract with hierarchy so subheadings under Uses inherit context."""
    found = list(HEADING.finditer(text))
    if not found:
        return text.strip(), []

    intro = text[:found[0].start()].strip()
    sections = []
    parent_l2 = ""

    for i, m in enumerate(found):
        level = len(m.group(1))
        h_title = m.group(2).strip()
        if level == 2:
            parent_l2 = h_title

        start_pos = m.end()
        end_pos = found[i + 1].start() if i + 1 < len(found) else len(text)
        body = text[start_pos:end_pos].strip()

        # Clean body by removing trailing or embedded lower sub-headings if any
        if not body and i + 1 < len(found):
            continue

        sections.append({
            "level": level,
            "title": h_title,
            "parent": parent_l2,
            "body": body,
        })
    return intro, sections


def plant_info(scientific_name: str, common_names: list = None, family: str = None):
    """Compile rich botanical information, guaranteed to have uses and benefits on the page."""
    common_names = common_names or []
    family = family or ""
    family_lower = family.lower()

    # Build search candidates: species, common names, genus
    candidates = [scientific_name]
    clean_species = scientific_name.split("(")[0].strip()
    if clean_species not in candidates:
        candidates.append(clean_species)
    for c in common_names[:3]:
        if c and c not in candidates:
            candidates.append(c)
    genus = scientific_name.split()[0]
    if genus not in candidates:
        candidates.append(genus)

    wiki_title, text = None, None
    for cand in candidates:
        wiki_title, text = search_wiki(cand)
        if text and len(text) > 200:
            break

    uses_medicinal = []
    uses_culinary = []
    uses_domestic = []
    cautions = []
    care_guide = []
    summary = ""
    wiki_dist_text = ""

    if text:
        intro, sections = parse_hierarchical_sections(text)
        summary = clip(intro, 700)

        for s in sections:
            body = s["body"]
            if not body or len(body) < 25:
                continue

            h_title = s["title"]
            parent = s["parent"]
            combo_text = f"{parent} {h_title} {body[:200]}".lower()

            # Format title nicely
            display_title = f"{parent}: {h_title}" if (s["level"] > 2 and parent and parent.lower() not in h_title.lower()) else h_title

            if any(w in combo_text for w in DISTRIBUTION_WORDS) and not wiki_dist_text:
                wiki_dist_text = body
            elif any(w in combo_text for w in WARN_WORDS):
                if len(cautions) < 2:
                    cautions.append({"title": display_title, "text": clip(body, 500)})
            elif any(w in combo_text for w in MEDICINAL_WORDS):
                if len(uses_medicinal) < 2:
                    uses_medicinal.append({"title": display_title, "text": clip(body, 600)})
            elif any(w in combo_text for w in CULINARY_WORDS):
                if len(uses_culinary) < 2:
                    uses_culinary.append({"title": display_title, "text": clip(body, 600)})
            elif any(w in combo_text for w in DOMESTIC_WORDS):
                if len(uses_domestic) < 2:
                    uses_domestic.append({"title": display_title, "text": clip(body, 600)})

    # Fallback to Family / Botanical Knowledge Base if any section is empty
    fam_profile = BOTANICAL_FAMILY_PROFILES.get(family_lower) or GENERIC_BOTANICAL_PROFILE

    if not summary:
        common_desc = f" ({common_names[0]})" if common_names else ""
        summary = (
            f"{scientific_name}{common_desc} is a notable botanical specimen belonging to the {family} family. "
            f"It is appreciated by botanists and enthusiasts for its distinctive leaf architecture, foliage vitality, "
            f"and ecological significance in nature."
        )

    if not uses_medicinal:
        uses_medicinal.extend(fam_profile.get("medicinal", GENERIC_BOTANICAL_PROFILE["medicinal"])[:2])

    if not uses_culinary:
        uses_culinary.extend(fam_profile.get("culinary", GENERIC_BOTANICAL_PROFILE["culinary"])[:2])

    if not uses_domestic:
        uses_domestic.extend(fam_profile.get("domestic", GENERIC_BOTANICAL_PROFILE["domestic"])[:2])

    if not care_guide:
        care_guide.extend(fam_profile.get("care", GENERIC_BOTANICAL_PROFILE["care"])[:2])

    if not cautions and fam_profile.get("cautions"):
        cautions.extend(fam_profile.get("cautions")[:1])

    # Determine quick specs based on family and taxonomy
    specs_map = {
        "araceae": {"sunlight": "Bright Indirect Light", "watering": "Moderate (Dry Topsoil)", "pet_friendly": False, "pet_note": "Toxic to Cats & Dogs", "plant_type": "Tropical Aroid", "difficulty": "Easy to Moderate"},
        "lamiaceae": {"sunlight": "Full Sun (6+ hrs)", "watering": "Regular (Drain Well)", "pet_friendly": True, "pet_note": "Pet Safe Foliage", "plant_type": "Aromatic Herb", "difficulty": "Beginner Friendly"},
        "asphodelaceae": {"sunlight": "Bright Direct/Indirect", "watering": "Low (Soak & Dry)", "pet_friendly": False, "pet_note": "Mildly Toxic to Pets", "plant_type": "Succulent", "difficulty": "Low Maintenance"},
        "moraceae": {"sunlight": "Bright Indirect", "watering": "Moderate (Weekly)", "pet_friendly": False, "pet_note": "Sap Irritant to Pets", "plant_type": "Foliage Tree/Shrub", "difficulty": "Moderate"},
        "meliaceae": {"sunlight": "Full Sun", "watering": "Drought Tolerant", "pet_friendly": None, "pet_note": "Caution with Pets", "plant_type": "Hardwood Tree", "difficulty": "Hardy & Resilient"},
        "rutaceae": {"sunlight": "Full Sun (6-8 hrs)", "watering": "Moderate", "pet_friendly": False, "pet_note": "Oils Toxic to Pets", "plant_type": "Citrus Tree/Shrub", "difficulty": "Moderate"},
        "fabaceae": {"sunlight": "Full Sun", "watering": "Moderate", "pet_friendly": True, "pet_note": "Mostly Non-Toxic", "plant_type": "Legume / Shrub", "difficulty": "Beginner Friendly"},
        "rosaceae": {"sunlight": "Full Sun", "watering": "Regular", "pet_friendly": True, "pet_note": "Pet Safe Leaves", "plant_type": "Flowering Shrub/Tree", "difficulty": "Moderate"},
        "asteraceae": {"sunlight": "Full Sun", "watering": "Moderate", "pet_friendly": True, "pet_note": "Non-Toxic to Pets", "plant_type": "Flowering Herb", "difficulty": "Easy"},
        "malvaceae": {"sunlight": "Full to Partial Sun", "watering": "Regular Moist", "pet_friendly": True, "pet_note": "Pet Safe Foliage", "plant_type": "Flowering Shrub", "difficulty": "Easy"},
        "myrtaceae": {"sunlight": "Full Sun", "watering": "Low to Moderate", "pet_friendly": False, "pet_note": "Oils Toxic to Pets", "plant_type": "Aromatic Tree/Shrub", "difficulty": "Hardy"},
        "crassulaceae": {"sunlight": "Bright Filtered Light", "watering": "Low (Dry Soil)", "pet_friendly": False, "pet_note": "Mildly Toxic to Pets", "plant_type": "Succulent", "difficulty": "Low Maintenance"},
    }
    quick_specs = specs_map.get(family_lower, {
        "sunlight": "Bright Indirect Light",
        "watering": "Moderate (Dry Topsoil)",
        "pet_friendly": None,
        "pet_note": "Check Variety For Pets",
        "plant_type": f"{family} Specimen" if family else "Botanical Specimen",
        "difficulty": "Moderate"
    })

    # Combined legacy uses list for backwards compatibility
    all_uses = []
    for item in uses_medicinal:
        all_uses.append({"title": f"🌿 {item['title']}", "text": item["text"]})
    for item in uses_culinary:
        all_uses.append({"title": f"🍵 {item['title']}", "text": item["text"]})
    for item in uses_domestic:
        all_uses.append({"title": f"🏡 {item['title']}", "text": item["text"]})

    source_url = "https://en.wikipedia.org/wiki/" + (wiki_title or scientific_name).replace(" ", "_")

    distribution = resolve_plant_distribution(
        scientific_name=scientific_name,
        common_names=common_names,
        family=family,
        wiki_dist_text=wiki_dist_text
    )

    return {
        "summary": summary,
        "uses": all_uses,
        "uses_medicinal": uses_medicinal,
        "uses_culinary": uses_culinary,
        "uses_domestic": uses_domestic,
        "care_guide": care_guide,
        "cautions": cautions,
        "quick_specs": quick_specs,
        "distribution": distribution,
        "source_url": source_url,
        "wiki_title": wiki_title or scientific_name,
    }


# ---------------------------------------------------------------- routes
@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/identify")
def identify():
    upload = request.files.get("image")
    if upload is None:
        return jsonify(ok=False, message=NOT_LEAF_MESSAGE), 400
    jpeg = prepare_image(upload.read())
    if jpeg is None:
        return jsonify(ok=False, message=NOT_LEAF_MESSAGE), 400
    if not PLANTNET_KEY:
        return jsonify(ok=False, message="Server setup incomplete: add PLANTNET_API_KEY to .env."), 500

    try:
        results = plantnet_identify(jpeg)
    except requests.HTTPError as err:
        code = err.response.status_code
        message = {
            401: "The Pl@ntNet API key is invalid.",
            403: "The Pl@ntNet API key is not allowed to do this.",
            429: "Daily identification limit reached. Try again tomorrow.",
        }.get(code, "The plant service returned an error. Try again.")
        return jsonify(ok=False, message=message), 502
    except requests.RequestException:
        return jsonify(ok=False, message="Could not reach the plant service. Check your connection."), 502

    # Not a leaf (or not a plant at all): nothing found, or the match is weak.
    if not results or results[0].get("score", 0) < MIN_SCORE:
        return jsonify(ok=False, not_leaf=True, message=NOT_LEAF_MESSAGE), 422

    top = results[0]
    species = top["species"]
    name = species["scientificNameWithoutAuthor"]
    common_names = species.get("commonNames", [])[:5]
    family = species.get("family", {}).get("scientificNameWithoutAuthor", "")
    images = top.get("images") or []
    plant = {
        "scientific_name": name,
        "common_names": common_names,
        "family": family,
        "confidence": round(top["score"] * 100),
        "reference_image": images[0]["url"]["m"] if images else None,
    }
    alternatives = [
        {"scientific_name": r["species"]["scientificNameWithoutAuthor"],
         "common_name": (r["species"].get("commonNames") or [None])[0],
         "confidence": round(r["score"] * 100)}
        for r in results[1:4]
    ]
    return jsonify(
        ok=True,
        plant=plant,
        alternatives=alternatives,
        info=plant_info(name, common_names=common_names, family=family),
        lens=google_lens_matches(jpeg),
    )


@app.errorhandler(413)
def too_large(_):
    return jsonify(ok=False, message=f"Image is larger than {MAX_UPLOAD_MB} MB. Upload a smaller photo."), 413


if __name__ == "__main__":
    app.run(debug=True)
