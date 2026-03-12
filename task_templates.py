"""
Task templates for AI-powered task generation.
Each category contains ~100 eco-friendly tasks focused on sustainability.
"""
import uuid

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
            "points": 60,
            "estimatedImpact": "Saves ~2.4kg CO₂",
            "co2Kg": 2.4
        },
        {
            "title": "🚌 Use Public Transport",
            "details": "Share your carbon footprint by taking the bus, metro, or tram instead of a personal car.",
            "points": 40,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        },
        {
            "title": "🚶 Short Distance Walk",
            "details": "Walk instead of driving for distances under 2 km.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🤝 Carpool",
            "details": "Share your ride with a colleague or friend on your way to work or school.",
            "points": 30,
            "estimatedImpact": "Saves ~1.2kg CO₂",
            "co2Kg": 1.2
        },
        {
            "title": "🛴 Use Electric Scooter",
            "details": "Choose an e-scooter over a taxi for short trips within the city.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🚀 Use Cruise Control",
            "details": "Using cruise control on highways prevents sudden accelerations and reduces fuel consumption by 10%.",
            "points": 20,
            "estimatedImpact": "Saves ~0.8kg CO₂",
            "co2Kg": 0.8
        },
        {
            "title": "⚖️ Remove Excess Weight",
            "details": "Clear unnecessary items from your car trunk (every extra 45kg uses 2% more fuel).",
            "points": 5,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "💨 Check Tire Pressure",
            "details": "Low tire pressure increases friction and fuel consumption; check it today.",
            "points": 10,
            "estimatedImpact": "Saves ~0.4kg CO₂",
            "co2Kg": 0.4
        },
        {
            "title": "🛑 Avoid Idling",
            "details": "Turn off the engine if you are stopping for more than 1 minute to avoid unnecessary exhaust fumes.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🚆 Train over Plane",
            "details": "Choose the train over flying for domestic travel whenever possible; it's much eco-friendlier.",
            "points": 100,
            "estimatedImpact": "Saves ~5.0kg CO₂",
            "co2Kg": 5.0
        },
        {
            "title": "🏠 Work from Home",
            "details": "Eliminate commute emissions by working from home today if your job allows.",
            "points": 80,
            "estimatedImpact": "Saves ~4.0kg CO₂",
            "co2Kg": 4.0
        },
        {
            "title": "🛒 Bulk Grocery Shopping",
            "details": "Shop weekly instead of daily to reduce transport emissions.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        }
    ],
    "Energy": [
        {
            "title": "💡 Switch to LED Bulbs",
            "details": "Replace an old incandescent bulb with an LED that consumes 80% less energy.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🌑 Turn Off Lights",
            "details": "Make it a habit to strictly turn off lights when leaving a room today.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "🌡️ Lower Thermostat by 1°C",
            "details": "Lowering the thermostat by just 1 degree in winter saves 7% on energy.",
            "points": 45,
            "estimatedImpact": "Saves ~1.8kg CO₂",
            "co2Kg": 1.8
        },
        {
            "title": "❄️ Wash Clothes in Cold Water",
            "details": "Wash your clothes in cold water instead of 30°C or 40°C.",
            "points": 15,
            "estimatedImpact": "Saves ~0.6kg CO₂",
            "co2Kg": 0.6
        },
        {
            "title": "👕 Skip the Dryer",
            "details": "Air dry your clothes instead of using a machine to save massive amounts of energy.",
            "points": 50,
            "estimatedImpact": "Saves ~2.0kg CO₂",
            "co2Kg": 2.0
        },
        {
            "title": "🔌 Unplug Electronics (Vampire Power)",
            "details": "Unplug unused TVs, computers, and devices to prevent standby power consumption.",
            "points": 5,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "☀️ Use Natural Light",
            "details": "Open curtains fully during the day and avoid using artificial light.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🍽️ Run Full Dishwasher Loads",
            "details": "Wait until the dishwasher is full before running it to ensure water and energy efficiency.",
            "points": 10,
            "estimatedImpact": "Saves ~0.4kg CO₂",
            "co2Kg": 0.4
        },
        {
            "title": "💻 Sleep Mode for Computer",
            "details": "Use sleep mode instead of screensavers during short breaks.",
            "points": 5,
            "estimatedImpact": "Saves ~0.15kg CO₂",
            "co2Kg": 0.15
        },
        {
            "title": "🍲 Cook with Lid On",
            "details": "Keep the pot lid on while cooking to reduce cooking time and energy use.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🚫 Don't Open Oven Door",
            "details": "Avoid opening the oven door to check food; prevent heat loss.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "☕ Boil Only Needed Water",
            "details": "Only boil as much water as you need for your drink, not more.",
            "points": 5,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "🧹 Clean Fridge Coils",
            "details": "Clean the dusty coils at the back of your fridge to increase its efficiency.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        }
    ],
    "Food": [
        {
            "title": "🥗 Meat-Free Day (Vegetarian)",
            "details": "Eating meat-free for a day significantly reduces your carbon footprint.",
            "points": 85,
            "estimatedImpact": "Saves ~3.5kg CO₂",
            "co2Kg": 3.5
        },
        {
            "title": "🌱 Plant-Based Day (Vegan)",
            "details": "Maximize your impact by consuming no animal products today.",
            "points": 100,
            "estimatedImpact": "Saves ~4.5kg CO₂",
            "co2Kg": 4.5
        },
        {
            "title": "🚜 Eat Local Food",
            "details": "Shop from local producers or markets to reduce transport emissions.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "📅 Eat Seasonally",
            "details": "Consume seasonal vegetables that don't require greenhouse heating.",
            "points": 15,
            "estimatedImpact": "Saves ~0.6kg CO₂",
            "co2Kg": 0.6
        },
        {
            "title": "🍲 Upcycle Leftovers",
            "details": "Turn leftover food into a new meal instead of throwing it away.",
            "points": 25,
            "estimatedImpact": "Saves ~1.0kg CO₂",
            "co2Kg": 1.0
        },
        {
            "title": "🥡 Reduce Packaged Food",
            "details": "Buy in bulk or loose items instead of excessively packaged products.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🥤 Use Reusable Coffee Cup",
            "details": "Prevent waste by using your own thermos instead of a paper cup.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "👨‍🍳 Cook at Home",
            "details": "Cook at home instead of ordering out (saving courier + packaging emissions).",
            "points": 20,
            "estimatedImpact": "Saves ~0.8kg CO₂",
            "co2Kg": 0.8
        },
        {
            "title": "🍽️ Control Portions",
            "details": "Take only what you can eat to prevent food waste on your plate.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🍂 Compost Organic Waste",
            "details": "Return organic waste to the soil instead of the trash bin.",
            "points": 20,
            "estimatedImpact": "Saves ~0.7kg CO₂",
            "co2Kg": 0.7
        },
        {
            "title": "🥜 Eat Legumes",
            "details": "Eat lentils or chickpeas as a protein source instead of meat.",
            "points": 40,
            "estimatedImpact": "Saves ~1.5kg CO₂",
            "co2Kg": 1.5
        }
    ],
    "Waste": [
        {
            "title": "🛍️ Use Cloth Bags",
            "details": "Don't take plastic bags when shopping; use your own cloth bag.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "💧 Refuse Plastic Bottles",
            "details": "Use a flask/canteen and refuse single-use plastic water bottles.",
            "points": 5,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "📄 Use Both Sides of Paper",
            "details": "Use both sides of the paper at the office or school.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🔋 Recycle Batteries",
            "details": "Dispose of batteries in battery recycling bins, not regular trash.",
            "points": 25,
            "estimatedImpact": "Saves ~1.0kg CO₂",
            "co2Kg": 1.0
        },
        {
            "title": "🥛 Choose Glass Bottles",
            "details": "Prefer products in glass packaging over plastic.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🍹 Refuse Straws",
            "details": "Refuse plastic straws; drink without one or use a reusable one.",
            "points": 5,
            "estimatedImpact": "Saves ~0.02kg CO₂",
            "co2Kg": 0.02
        },
        {
            "title": "🧵 Repair Clothes",
            "details": "Sew torn clothes or fix buttons instead of throwing them away.",
            "points": 75,
            "estimatedImpact": "Saves ~3.0kg CO₂",
            "co2Kg": 3.0
        },
        {
            "title": "🧥 Buy Second Hand",
            "details": "Choose second-hand or vintage items instead of new clothes.",
            "points": 100,
            "estimatedImpact": "Saves ~4.0kg CO₂",
            "co2Kg": 4.0
        },
        {
            "title": "🔌 Recycle E-Waste",
            "details": "Take old cables and phones to an e-waste collection center.",
            "points": 50,
            "estimatedImpact": "Saves ~2.0kg CO₂",
            "co2Kg": 2.0
        },
        {
            "title": "🐝 Skip Cling Film",
            "details": "Use beeswax wraps or containers with lids instead of cling film.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "🧼 Use Shampoo Bar",
            "details": "Use a solid shampoo bar instead of shampoo in plastic bottles.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "📨 Opt for Digital Invoices",
            "details": "Request e-invoices instead of paper bills.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        }
    ],
    "Water": [
        {
            "title": "⏱️ Shorten Shower Time",
            "details": "Try to keep your shower under 5 minutes today.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🪥 Turn Off Tap While Brushing",
            "details": "Don't leave the tap running while brushing your teeth.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🔧 Fix Leaky Faucets",
            "details": "A dripping tap wastes liters of water a day; fix it or get it fixed.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        },
        {
            "title": "🌧️ Harvest Rainwater",
            "details": "Collect rainwater to water the plants on your balcony.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🧼 Use Dishwasher",
            "details": "The machine uses much less water than hand washing. Fill it up and run it.",
            "points": 10,
            "estimatedImpact": "Saves ~0.4kg CO₂",
            "co2Kg": 0.4
        },
        {
            "title": "🥬 Wash Veggies in a Bowl",
            "details": "Wash vegetables in a bowl of water, not under running water.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🚽 Water Bottle in Cistern",
            "details": "Place a filled water bottle in the toilet cistern to save water with every flush.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🚿 Collect Cold Shower Water",
            "details": "Collect the cold water that runs while waiting for the shower to warm up and use it for cleaning.",
            "points": 5,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        }
    ],
    "Digital": [
        {
            "title": "📧 Clean Up Emails",
            "details": "Deleting unnecessary emails and spam reduces server energy consumption.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🌙 Use Dark Mode",
            "details": "Dark mode saves energy on OLED screens.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂",
            "co2Kg": 0.05
        },
        {
            "title": "📉 Lower Video Quality",
            "details": "Watch videos in 720p instead of 4K on your phone.",
            "points": 5,
            "estimatedImpact": "Saves ~0.2kg CO₂",
            "co2Kg": 0.2
        },
        {
            "title": "☁️ Manage Cloud Storage",
            "details": "Delete unnecessary large files from the cloud to reduce data center load.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂",
            "co2Kg": 0.1
        },
        {
            "title": "🔍 Navigate Directly",
            "details": "Type the URL directly into the address bar instead of searching for sites you visit often.",
            "points": 5,
            "estimatedImpact": "Saves ~0.02kg CO₂",
            "co2Kg": 0.02
        }
    ],
    "Social": [
        {
            "title": "🌳 Join Tree Planting Event",
            "details": "Physically participate in planting saplings or make a donation.",
            "points": 100,
            "estimatedImpact": "Saves ~10.0kg CO₂",
            "co2Kg": 10.0
        },
        {
            "title": "🎥 Watch Sustainability Doc",
            "details": "Watch an environmental documentary to raise your awareness.",
            "points": 10,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "🗣️ Educate a Friend",
            "details": "Share this app or an eco-tip with a friend.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂",
            "co2Kg": 0.5
        },
        {
            "title": "📚 Read an Eco-Book",
            "details": "Read an article or book about climate change or nature.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂",
            "co2Kg": 0.3
        }
    ]
}