"""
AI-powered task templates for GreenHabit.
Focused on Kitchen Sustainability, Food Waste Reduction, and Resource Management.
Categories map to server defaults (Energy, Water, Waste, Transport) but with a food/kitchen focus.
"""
import uuid

TASK_POOL = {
    "Energy": [
        {
            "title": "🍳 Batch Cook Your Meals",
            "details": "Cook multiple meals at once to maximize oven/stove energy efficiency. Reheating uses significantly less energy than cooking from scratch every time.",
            "points": 20,
            "estimatedImpact": "Saves ~0.2kg CO₂"
        },
        {
            "title": "🧊 Thaw Food in the Fridge",
            "details": "Move frozen food to the fridge overnight to thaw. This reduces the energy your fridge needs to keep cool and saves cooking energy later.",
            "points": 10,
            "estimatedImpact": "Saves ~0.1kg CO₂"
        },
        {
            "title": "🔥 Match Pot to Burner Size",
            "details": "Using a small pot on a large burner wastes heat. Match the cookware to the burner size to prevent energy loss.",
            "points": 10,
            "estimatedImpact": "Saves ~0.15kg CO₂"
        },
        {
            "title": "☕ Boil Only Water You Need",
            "details": "When making tea or coffee, measure the water first. Boiling excess water is one of the biggest energy wasters in the kitchen.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂"
        },
        {
            "title": "🥘 Keep the Oven Door Shut",
            "details": "Avoid opening the oven door while cooking. Each opening drops the temperature by 25-50°F and forces the oven to work harder.",
            "points": 15,
            "estimatedImpact": "Saves ~0.2kg CO₂"
        },
        {
            "title": "🌬️ Air Dry Your Dishes",
            "details": "Turn off the 'heat dry' setting on your dishwasher and let the dishes air dry by opening the door slightly after the wash cycle.",
            "points": 15,
            "estimatedImpact": "Saves ~0.15kg CO₂"
        },
        {
            "title": "🌡️ Check Fridge Seals",
            "details": "Test your refrigerator door seals with a piece of paper. If it slides out easily, you are losing cold air and wasting electricity.",
            "points": 20,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🍲 Use a Pressure Cooker",
            "details": "Cook beans, stews, or meat in a pressure cooker. It speeds up cooking time drastically, saving huge amounts of energy.",
            "points": 25,
            "estimatedImpact": "Saves ~0.5kg CO₂"
        },
        {
            "title": "🧹 Clean Refrigerator Coils",
            "details": "Dusty coils force your fridge to work harder. Vacuum the coils at the back or bottom of your fridge.",
            "points": 30,
            "estimatedImpact": "Saves ~0.3kg CO₂"
        },
        {
            "title": "🍲 Put a Lid on It",
            "details": "Always cover your pots and pans while cooking. Water boils faster and food cooks quicker, using less gas or electricity.",
            "points": 10,
            "estimatedImpact": "Saves ~0.1kg CO₂"
        }
    ],
    "Water": [
        {
            "title": "🥣 Wash Produce in a Bowl",
            "details": "Instead of running the tap to wash fruits and veggies, fill a large bowl. Use the leftover water for your house plants!",
            "points": 15,
            "estimatedImpact": "Saves ~0.05kg CO₂e"
        },
        {
            "title": "🍽️ Run Full Dishwasher Loads",
            "details": "Wait until the dishwasher is completely full before running it. A full load is more water-efficient than hand washing.",
            "points": 10,
            "estimatedImpact": "Saves ~1.0kg CO₂e"
        },
        {
            "title": "💧 Save Cooking Water",
            "details": "Don't pour unsalted pasta or veggie boiling water down the drain. Let it cool and use it to water your garden or plants.",
            "points": 15,
            "estimatedImpact": "Saves ~0.02kg CO₂e"
        },
        {
            "title": "🥩 Defrost Without Water",
            "details": "Avoid thawing frozen foods under running water. Plan ahead and thaw in the fridge to save gallons of water.",
            "points": 15,
            "estimatedImpact": "Saves ~0.05kg CO₂e"
        },
        {
            "title": "🧽 Soak Pots, Don't Scrub",
            "details": "Soak dirty pots and pans in soapy water instead of scrubbing them under a running tap.",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂e"
        },
        {
            "title": "🥬 Steam Instead of Boil",
            "details": "Steaming vegetables uses significantly less water than boiling them, and it preserves more nutrients.",
            "points": 10,
            "estimatedImpact": "Saves ~0.1kg CO₂e"
        },
        {
            "title": "🧊 Keep Water in the Fridge",
            "details": "Keep a jug of water in the fridge so you don't have to run the tap waiting for it to get cold.",
            "points": 5,
            "estimatedImpact": "Saves ~0.02kg CO₂e"
        },
        {
            "title": "🔧 Fix the Kitchen Drip",
            "details": "Check your kitchen faucet for drips. Even a slow drip wastes an incredible amount of water over time.",
            "points": 25,
            "estimatedImpact": "Saves ~0.05kg CO₂e/day"
        },
        {
            "title": "🥤 Use One Glass All Day",
            "details": "Designate one glass for water drinking throughout the day to reduce the number of items that need washing.",
            "points": 5,
            "estimatedImpact": "Saves ~0.05kg CO₂e"
        },
        {
            "title": "🚿 Install a Tap Aerator",
            "details": "Install a simple aerator on your kitchen tap. It maintains pressure while reducing flow rate significantly.",
            "points": 30,
            "estimatedImpact": "Saves ~0.5kg CO₂e/day"
        }
    ],
    "Waste": [
        {
            "title": "📅 Eat the 'Use-By' First",
            "details": "Check your fridge for items nearing their expiration date and plan today's meal around saving them from the bin.",
            "points": 20,
            "estimatedImpact": "Saves ~1.5kg CO₂e"
        },
        {
            "title": "🍌 Buy 'Ugly' Produce",
            "details": "Choose misshapen fruits and vegetables at the store. They taste the same but are often discarded due to looks.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂e"
        },
        {
            "title": "🥡 Pack a Zero-Waste Lunch",
            "details": "Use reusable containers, beeswax wraps, and real cutlery for your lunch today. No single-use plastics!",
            "points": 15,
            "estimatedImpact": "Saves ~0.2kg CO₂"
        },
        {
            "title": "🥕 Start a Scrap Broth Bag",
            "details": "Keep a bag in the freezer for vegetable peels, ends, and stalks. When full, boil them to make free vegetable stock.",
            "points": 20,
            "estimatedImpact": "Saves ~1.0kg CO₂e"
        },
        {
            "title": "☕ Use Coffee Grounds",
            "details": "Don't trash coffee grounds! Use them as a skin exfoliant or add them to soil for acid-loving plants.",
            "points": 10,
            "estimatedImpact": "Saves ~0.1kg CO₂e"
        },
        {
            "title": "♻️ Compost Kitchen Scraps",
            "details": "Put your fruit and vegetable peels in a compost bin instead of the trash. It returns nutrients to the earth.",
            "points": 25,
            "estimatedImpact": "Saves ~2.0kg CO₂e"
        },
        {
            "title": "🛍️ Bulk Buy Dry Goods",
            "details": "Buy rice, pasta, or beans in the largest package available or from bulk bins to reduce packaging waste per serving.",
            "points": 15,
            "estimatedImpact": "Saves ~0.1kg CO₂"
        },
        {
            "title": "🥖 Revive Stale Bread",
            "details": "Don't toss stale bread! Make croutons, breadcrumbs, or French toast instead.",
            "points": 15,
            "estimatedImpact": "Saves ~0.8kg CO₂e"
        },
        {
            "title": "🥣 Eat Leftovers Night",
            "details": "Dedicate tonight's dinner to clearing out leftovers from the fridge. It's an easy meal and saves food.",
            "points": 20,
            "estimatedImpact": "Saves ~1.5kg CO₂e"
        },
        {
            "title": "🥤 Refuse Plastic Straws/Cutlery",
            "details": "If ordering takeout, explicitly request 'no cutlery' and 'no straws' in the notes.",
            "points": 10,
            "estimatedImpact": "Saves ~0.05kg CO₂"
        }
    ],
    "Transport": [
        {
            "title": "🚶 Walk for Groceries",
            "details": "If you only need a few items, walk to the local market instead of driving to the big supermarket.",
            "points": 20,
            "estimatedImpact": "Saves ~0.5kg CO₂"
        },
        {
            "title": "🥬 Buy Local & Seasonal",
            "details": "Check labels and buy produce grown in your country/region. Reduces 'food miles' significantly.",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂"
        },
        {
            "title": "📝 Make a Shopping List",
            "details": "Stick to a list to avoid forgetting items and having to make a second trip back to the store later.",
            "points": 10,
            "estimatedImpact": "Saves ~1.5kg CO₂"
        },
        {
            "title": "🎒 Bring Your Own Bag",
            "details": "Remember your reusable tote bags for shopping. Keep them by the door or in your car.",
            "points": 10,
            "estimatedImpact": "Saves ~0.05kg CO₂"
        },
        {
            "title": "🚛 Choose Standard Shipping",
            "details": "When ordering kitchen supplies online, choose slower shipping. Express shipping often requires inefficient transport.",
            "points": 10,
            "estimatedImpact": "Saves ~0.5kg CO₂"
        },
        {
            "title": "🥩 Try a Meat-Free Day",
            "details": "Meat production requires massive transport and resources. Skipping meat for one day reduces your dietary carbon footprint.",
            "points": 30,
            "estimatedImpact": "Saves ~2.0kg CO₂e"
        },
        {
            "title": "🥚 Buy Eggs from a Local Farm",
            "details": "If possible, buy eggs or dairy from a nearby farm or farmer's market to support local logistics.",
            "points": 20,
            "estimatedImpact": "Saves ~0.3kg CO₂"
        },
        {
            "title": "📦 Buy Concentrated Products",
            "details": "Buy concentrated cleaning refills. They are smaller and lighter to transport than full bottles of water-heavy cleaner.",
            "points": 15,
            "estimatedImpact": "Saves ~0.2kg CO₂"
        },
        {
            "title": "🚲 Bike to the Bakery",
            "details": "Use your bicycle for your morning bread run or small errands.",
            "points": 20,
            "estimatedImpact": "Saves ~0.8kg CO₂"
        },
        {
            "title": "🍽️ Eat at a Local Restaurant",
            "details": "Choose a restaurant that sources ingredients locally to reduce the community's overall food transport footprint.",
            "points": 15,
            "estimatedImpact": "Saves ~1.0kg CO₂"
        }
    ]
}