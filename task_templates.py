"""
Task templates for AI-powered task generation.
Each category contains eco-friendly tasks focused on sustainability.

IMPORTANT: Points must satisfy the formula: points = min(100, ceil(co2Kg * 10))
The server recalculates points from co2Kg on task creation, so mismatched
values will cause a visible discrepancy in the UI (before vs after adding).

CO₂ figures are approximate, based on published datasets (IPCC, Our World in Data,
ADEME, WRAP, UK Energy Saving Trust). They represent the per-action saving for a
typical household/individual and are intentionally conservative.
"""
import re

def parse_co2_impact(impact_str: str) -> float:
    """Parse numeric CO2 kg from estimatedImpact string"""
    if not impact_str:
        return 0.3
    match = re.search(r'([0-9.]+)\s*kg', str(impact_str), re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0.3

TASK_POOL = {
    "Transport": [
        {
            "title": "🚲 Bike to Work",
            "details": "Use a bicycle instead of a motor vehicle today to ensure zero emissions and get some exercise.",
            "points": 24,
            "estimatedImpact": "Saves ~2.4kg CO₂",
            "co2Kg": 2.4
        },
        {
            "title": "🚌 Use Public Transport",
            "details": "Share your carbon footprint by taking the bus, metro, or tram instead of a personal car.",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        },
        {
            "title": "🚶 Short Distance Walk",
            "details": "Walk instead of driving for distances under 2 km.",
            "points": 5,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🤝 Carpool",
            "details": "Share your ride with a colleague or friend on your way to work or school.",
            "points": 12,
            "estimatedImpact": "Saves ~1.2kg CO₂",
            "co2Kg": 1.2
        },
        {
            "title": "🛴 Use Electric Scooter",
            "details": "Choose an e-scooter over a taxi for short trips within the city.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🚗 Use Cruise Control",
            "details": "Using cruise control on highways prevents sudden accelerations and reduces fuel consumption by 10%.",
            "points": 8,
            "estimatedImpact": "Saves ~0.8kg CO₂",
            "co2Kg": 0.8
        },
        {
            "title": "⚖️ Remove Excess Weight",
            "details": "Clear unnecessary items from your car trunk (every extra 45kg uses 2% more fuel).",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "💨 Check Tire Pressure",
            "details": "Low tire pressure increases friction and fuel consumption; check it today.",
            "points": 4,
            "estimatedImpact": "Saves ~0.4kg CO₂",
            "co2Kg": 0.4
        },
        {
            "title": "🛑 Avoid Idling",
            "details": "Turn off the engine if you are stopping for more than 1 minute to avoid unnecessary exhaust fumes.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🚆 Train over Plane",
            "details": "Choose the train over flying for domestic travel whenever possible. For a 500km trip, rail produces roughly 10× fewer emissions per passenger than flying (approx. ~8kg CO₂ saved — a conservative estimate vs. the real-world ~50-80kg difference).",
            "points": 80,
            "estimatedImpact": "Saves ~8.0kg CO₂",
            "co2Kg": 8.0
        },
        {
            "title": "🏠 Work from Home",
            "details": "Eliminate commute emissions by working from home today if your job allows.",
            "points": 40,
            "estimatedImpact": "Saves ~4.0kg CO₂",
            "co2Kg": 4.0
        },
        {
            "title": "🛒 Bulk Grocery Shopping",
            "details": "Shop weekly instead of daily to reduce transport emissions.",
            "points": 5,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🚗 Plan a No-Drive Day",
            "details": "Commit to using no motor vehicles today — walk, cycle, or take transit for every trip. Avoiding a typical 20km daily commute by car saves roughly 4kg CO₂ (approx. 0.2kg/km).",
            "points": 40,
            "estimatedImpact": "Saves ~4.0kg CO₂",
            "co2Kg": 4.0
        },
        {
            "title": "🗺️ Combine Errands in One Trip",
            "details": "Plan all errands into a single efficient loop instead of making multiple separate trips. Consolidating ~7km of otherwise separate journeys saves fuel and time.",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        }
    ],
    "Energy": [
        {
            "title": "💡 Switch to LED Bulbs",
            "details": "Replace an old incandescent bulb with an LED that consumes 80% less energy.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🌑 Turn Off Lights",
            "details": "Make it a habit to strictly turn off lights when leaving a room today.",
            "points": 1,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "🌡️ Lower Thermostat by 1°C",
            "details": "Lowering the thermostat by just 1 degree in winter saves 7% on energy.",
            "points": 18,
            "estimatedImpact": "Saves ~1.8kg CO₂",
            "co2Kg": 1.8
        },
        {
            "title": "❄️ Wash Clothes in Cold Water",
            "details": "Wash your clothes in cold water instead of 30°C or 40°C.",
            "points": 6,
            "estimatedImpact": "Saves ~0.6kg CO₂",
            "co2Kg": 0.6
        },
        {
            "title": "👕 Skip the Dryer",
            "details": "Air dry your clothes instead of using a machine to save massive amounts of energy.",
            "points": 20,
            "estimatedImpact": "Saves ~2.0kg CO₂",
            "co2Kg": 2.0
        },
        {
            "title": "🔌 Unplug Electronics (Vampire Power)",
            "details": "Unplug unused TVs, computers, and devices to prevent standby power consumption.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "☀️ Use Natural Light",
            "details": "Open curtains fully during the day and avoid using artificial light.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🍽️ Run Full Dishwasher Loads",
            "details": "Wait until the dishwasher is full before running it to ensure water and energy efficiency.",
            "points": 4,
            "estimatedImpact": "Saves ~0.4kg CO₂",
            "co2Kg": 0.4
        },
        {
            "title": "💻 Sleep Mode for Computer",
            "details": "Use sleep mode instead of screensavers during short breaks.",
            "points": 2,
            "estimatedImpact": "Saves ~0.15kg CO₂",
            "co2Kg": 0.15
        },
        {
            "title": "🍲 Cook with Lid On",
            "details": "Keep the pot lid on while cooking to reduce cooking time and energy use.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🚫 Don't Open Oven Door",
            "details": "Avoid opening the oven door to check food; prevent heat loss.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "☕ Boil Only Needed Water",
            "details": "Only boil as much water as you need for your drink, not more.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "🧹 Clean Fridge Coils",
            "details": "Clean the dusty coils at the back of your fridge to increase its efficiency.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🌡️ Program a Thermostat Schedule",
            "details": "Set heating/cooling to match occupancy hours — lower overnight and off when you are out. Scheduling alone saves ~10–15% of heating energy, roughly 1.5kg CO₂/day for an average home (UK Energy Saving Trust estimate).",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        },
        {
            "title": "☀️ Switch to a Green Energy Tariff",
            "details": "Contact your energy provider and switch to a renewable electricity tariff today. An average EU household uses ~20kWh/day; switching from a coal-heavy grid (0.25kg CO₂/kWh) to renewables avoids ~5kg CO₂ per day.",
            "points": 50,
            "estimatedImpact": "Saves ~5.0kg CO₂",
            "co2Kg": 5.0
        }
    ],
    "Food": [
        {
            "title": "🥗 Meat-Free Day (Vegetarian)",
            "details": "Eating meat-free for a day significantly reduces your carbon footprint.",
            "points": 35,
            "estimatedImpact": "Saves ~3.5kg CO₂",
            "co2Kg": 3.5
        },
        {
            "title": "🌱 Plant-Based Day (Vegan)",
            "details": "Maximize your impact by consuming no animal products today.",
            "points": 45,
            "estimatedImpact": "Saves ~4.5kg CO₂",
            "co2Kg": 4.5
        },
        {
            "title": "🚜 Eat Local Food",
            "details": "Shop from local producers or markets to reduce transport emissions.",
            "points": 5,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "📅 Eat Seasonally",
            "details": "Consume seasonal vegetables that don't require greenhouse heating.",
            "points": 6,
            "estimatedImpact": "Saves ~0.6kg CO₂",
            "co2Kg": 0.6
        },
        {
            "title": "🍲 Upcycle Leftovers",
            "details": "Turn leftover food into a new meal instead of throwing it away.",
            "points": 10,
            "estimatedImpact": "Saves ~1.0kg CO₂",
            "co2Kg": 1.0
        },
        {
            "title": "🥡 Reduce Packaged Food",
            "details": "Buy in bulk or loose items instead of excessively packaged products.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🥤 Use Reusable Coffee Cup",
            "details": "Prevent waste by using your own thermos instead of a paper cup.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "👨‍🍳 Cook at Home",
            "details": "Cook at home instead of ordering out (saving courier + packaging emissions).",
            "points": 8,
            "estimatedImpact": "Saves ~0.8kg CO₂",
            "co2Kg": 0.8
        },
        {
            "title": "🍽️ Control Portions",
            "details": "Take only what you can eat to prevent food waste on your plate.",
            "points": 5,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🍂 Compost Organic Waste",
            "details": "Return organic waste to the soil instead of the trash bin.",
            "points": 7,
            "estimatedImpact": "Saves ~0.7kg CO₂",
            "co2Kg": 0.7
        },
        {
            "title": "🥜 Eat Legumes",
            "details": "Eat lentils or chickpeas as a protein source instead of meat.",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        },
        {
            "title": "🌊 Choose Sustainably Sourced Seafood",
            "details": "Buy only MSC/ASC-certified fish or shellfish today to support responsible fishing and avoid destructive practices. Choosing sustainably sourced seafood saves approximately 0.8kg CO₂ versus the equivalent protein from beef.",
            "points": 8,
            "estimatedImpact": "Saves ~0.8kg CO₂",
            "co2Kg": 0.8
        },
        {
            "title": "🪴 Grow Your Own Herbs",
            "details": "Plant or tend basil, parsley, or mint at home — zero food miles, zero packaging. Growing your own eliminates the supply chain emissions of packaged herbs entirely.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        }
    ],
    "Waste": [
        {
            "title": "🛍️ Use Cloth Bags",
            "details": "Don't take plastic bags when shopping; use your own cloth bag.",
            "points": 1,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "💧 Refuse Plastic Bottles",
            "details": "Use a flask/canteen and refuse single-use plastic water bottles.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "📄 Use Both Sides of Paper",
            "details": "Use both sides of the paper at the office or school.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🔋 Recycle Batteries",
            "details": "Dispose of batteries in battery recycling bins, not regular trash.",
            "points": 10,
            "estimatedImpact": "Saves ~1.0kg CO₂",
            "co2Kg": 1.0
        },
        {
            "title": "🥛 Choose Glass Bottles",
            "details": "Prefer products in glass packaging over plastic.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🍹 Refuse Straws",
            "details": "Refuse plastic straws; drink without one or use a reusable one.",
            "points": 1,
            "estimatedImpact": "Saves ~0.02kg CO₂",
            "co2Kg": 0.02
        },
        {
            "title": "🧵 Repair Clothes",
            "details": "Sew torn clothes or fix buttons instead of throwing them away.",
            "points": 30,
            "estimatedImpact": "Saves ~3.0kg CO₂",
            "co2Kg": 3.0
        },
        {
            "title": "🧥 Buy Second Hand",
            "details": "Choose second-hand or vintage items instead of new clothes.",
            "points": 40,
            "estimatedImpact": "Saves ~4.0kg CO₂",
            "co2Kg": 4.0
        },
        {
            "title": "🔌 Recycle E-Waste",
            "details": "Take old cables and phones to an e-waste collection center.",
            "points": 20,
            "estimatedImpact": "Saves ~2.0kg CO₂",
            "co2Kg": 2.0
        },
        {
            "title": "🐝 Skip Cling Film",
            "details": "Use beeswax wraps or containers with lids instead of cling film.",
            "points": 1,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "🧼 Use Shampoo Bar",
            "details": "Use a solid shampoo bar instead of shampoo in plastic bottles.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "📨 Opt for Digital Invoices",
            "details": "Request e-invoices instead of paper bills.",
            "points": 1,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "♻️ Do a Proper Recycling Sort",
            "details": "Carefully sort all your household waste into the correct recycling bins today. Correctly sorted recyclables avoid landfill — approximately 1kg CO₂ per bag diverted from incineration or decomposition (WRAP UK estimate).",
            "points": 10,
            "estimatedImpact": "Saves ~1.0kg CO₂",
            "co2Kg": 1.0
        },
        {
            "title": "🧴 Switch to Refillable Products",
            "details": "Use concentrate refills for dish soap, hand soap, or surface cleaner instead of buying new plastic bottles. Refillable systems avoid ~1.5kg CO₂ per bottle replaced (ADEME France data, approximate).",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        },
        {
            "title": "👕 Organise a Clothes Swap",
            "details": "Host or join a local clothing swap to extend garment life without new production. Each garment that avoids manufacture saves approximately 5kg CO₂ on the marginal production footprint (WRAP lifecycle data).",
            "points": 50,
            "estimatedImpact": "Saves ~5.0kg CO₂",
            "co2Kg": 5.0
        }
    ],
    "Water": [
        {
            "title": "⏱️ Shorten Shower Time",
            "details": "Try to keep your shower under 5 minutes today.",
            "points": 5,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🪥 Turn Off Tap While Brushing",
            "details": "Don't leave the tap running while brushing your teeth.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🔧 Fix Leaky Faucets",
            "details": "A dripping tap wastes liters of water a day; fix it or get it fixed.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🌧️ Harvest Rainwater",
            "details": "Collect rainwater to water the plants on your balcony.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🧼 Use Dishwasher",
            "details": "The machine uses much less water than hand washing. Fill it up and run it.",
            "points": 4,
            "estimatedImpact": "Saves ~0.4kg CO₂",
            "co2Kg": 0.4
        },
        {
            "title": "🥬 Wash Veggies in a Bowl",
            "details": "Wash vegetables in a bowl of water, not under running water.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🚽 Water Bottle in Cistern",
            "details": "Place a filled water bottle in the toilet cistern to save water with every flush.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🚿 Collect Cold Shower Water",
            "details": "Collect the cold water that runs while waiting for the shower to warm up and use it for cleaning.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "🔍 Check Home for Water Leaks",
            "details": "Inspect all taps, pipes, and the toilet cistern for drips — fixing a single dripping tap can save over 200 litres per day, reducing water heating energy by approximately 0.5kg CO₂.",
            "points": 5,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🚿 Take a 2-Minute Navy Shower",
            "details": "Wet yourself, turn the water off, soap up, then turn it back on to rinse. Under 2 minutes total. A standard shower uses ~60L; a navy shower uses ~8L — the energy saved from heating that water saves roughly 0.6kg CO₂.",
            "points": 6,
            "estimatedImpact": "Saves ~0.6kg CO₂",
            "co2Kg": 0.6
        },
        {
            "title": "💧 Reuse Pasta or Vegetable Water",
            "details": "Let cooking water cool and use it to water your plants instead of pouring it down the drain. Nutrient-rich and free — zero extra tap use.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        }
    ],
    "Digital": [
        {
            "title": "📧 Clean Up Emails",
            "details": "Deleting unnecessary emails and spam reduces server energy consumption.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🌙 Use Dark Mode",
            "details": "Dark mode saves energy on OLED screens.",
            "points": 1,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "📉 Lower Video Quality",
            "details": "Watch videos in 720p instead of 4K on your phone.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "☁️ Manage Cloud Storage",
            "details": "Delete unnecessary large files from the cloud to reduce data center load.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "📵 Screen-Free Evening",
            "details": "Turn off all screens — TV, phone, and laptop — for at least 3 hours tonight. Beyond the direct energy saving, this reduces streaming data centre load and is good for your sleep.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🔆 Enable Auto-Brightness on All Devices",
            "details": "Let your phone and tablet automatically dim in low-light conditions. The screen accounts for ~30% of phone power consumption; auto-brightness saves an estimated 15–20% of that.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "📦 Consolidate Online Deliveries",
            "details": "Delay non-urgent purchases so they ship together in a single parcel rather than separate deliveries. Last-mile delivery accounts for ~0.5–1.0kg CO₂ per parcel; consolidation saves roughly 0.8kg on average (McKinsey logistics data, approximate).",
            "points": 8,
            "estimatedImpact": "Saves ~0.8kg CO₂",
            "co2Kg": 0.8
        },
        {
            "title": "📺 Disable Video Autoplay",
            "details": "Turn off video autoplay on social media and streaming platforms. Autoplay drives an estimated 10–15% of unnecessary video streaming, which contributes to data centre energy consumption and CO₂ emissions.",
            "points": 3,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        }
    ],
    "Social": [
        {
            "title": "🌳 Join Tree Planting Event",
            "details": "Physically participate in planting saplings or make a donation to a verified reforestation project. A single tree sequesters roughly 10kg CO₂ per year at maturity — the figure shown is a conservative lifetime-sequestration estimate for your contribution.",
            "points": 100,
            "estimatedImpact": "Saves ~10.0kg CO₂",
            "co2Kg": 10.0
        },
        {
            "title": "🎥 Watch Sustainability Doc",
            "details": "Watch an environmental documentary to raise your awareness. The CO₂ value reflects a small indirect benefit from raising climate literacy — not a direct emission saving.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "🗣️ Educate a Friend",
            "details": "Share this app or an evidence-based eco-tip with a friend. The CO₂ value is an approximate indirect benefit from spreading climate awareness — the real multiplier effect is hard to quantify.",
            "points": 2,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "📚 Read an Eco-Book",
            "details": "Read an article or book about climate change or nature. The CO₂ value is a symbolic indirect benefit — the real value is the knowledge and motivation gained.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🌱 Join a Community Clean-Up",
            "details": "Participate in a local park, beach, or street clean-up event today. Diverting ~10 bags of litter from incineration or landfill avoids roughly 2kg CO₂ (approx. 0.2kg CO₂ per bag, WRAP UK).",
            "points": 20,
            "estimatedImpact": "Saves ~2.0kg CO₂",
            "co2Kg": 2.0
        },
        {
            "title": "🗳️ Contact Your Local Representative",
            "details": "Write or call your MP, mayor, or councillor about a local environmental policy issue. This is an indirect action whose real value is in driving systemic change — the CO₂ figure is a minimal placeholder.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "💚 Support an Environmental Cause",
            "details": "Donate to or volunteer with a verified environmental NGO today. The CO₂ value is an approximate indirect benefit reflecting the leverage that well-run environmental organisations have on emissions at scale.",
            "points": 10,
            "estimatedImpact": "Saves ~1.0kg CO₂",
            "co2Kg": 1.0
        },
        {
            "title": "📣 Share an Eco-Tip Publicly",
            "details": "Post an evidence-based sustainability tip on social media or in a community group. A small indirect benefit — the CO₂ figure is intentionally low to remain honest about direct vs. facilitated savings.",
            "points": 1,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        }
    ]
}
