"""
Task templates for AI-powered task generation
Each category contains 10 eco-friendly task templates
"""
import uuid
TASK_POOL = {
    "Energy": [
        {
            "title": "💡 Turn off unused lights",
            "details": "Make it a habit to switch off all lights when leaving a room. Even a few seconds makes a difference!",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🔌 Unplug phone charger",
            "details": "Phone chargers consume 'phantom power' even when not charging. Unplug them to save energy!",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂/day"
        },
        {
            "title": "☀️ Use natural daylight",
            "details": "Open curtains and blinds during the day. Let the sun light your space instead of electric bulbs!",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🌡️ Set thermostat 1°C lower",
            "details": "Reducing your heating by just 1 degree can save significant energy over time without much discomfort.",
            "points": 15,
            "estimatedImpact": "Saves ~1.0kg CO₂/day"
        },
        {
            "title": "👕 Air dry laundry",
            "details": "Skip the dryer and hang your clothes to dry naturally. Saves energy and clothes last longer!",
            "points": 20,
            "estimatedImpact": "Saves ~2.5kg CO₂/load"
        },
        {
            "title": "🔋 Unplug all devices at night",
            "details": "Use a power strip and turn everything off before bed. Stop vampire energy drain!",
            "points": 15,
            "estimatedImpact": "Saves ~0.5kg CO₂/day"
        },
        {
            "title": "🪟 Close curtains at sunset",
            "details": "Keep heat inside during cold months. Simple insulation trick that really works!",
            "points": 10,
            "estimatedImpact": "Saves ~0.4kg CO₂/day"
        },
        {
            "title": "❄️ Clean refrigerator coils",
            "details": "Dusty coils make your fridge work harder. Clean them every 6 months for efficiency.",
            "points": 15,
            "estimatedImpact": "Improves efficiency 5%"
        },
        {
            "title": "🍳 Use lids when cooking",
            "details": "Cover pots and pans to cook faster and use less energy. Works with all types of stoves!",
            "points": 10,
            "estimatedImpact": "Saves ~0.2kg CO₂/meal"
        },
        {
            "title": "🖥️ Enable power saving mode",
            "details": "Activate energy-saving settings on your computer, phone, and other devices.",
            "points": 5,
            "estimatedImpact": "Saves ~0.1kg CO₂/day"
        },
    ],
    "Water": [
        {
            "title": "⏱️ Take 5-minute shower",
            "details": "Challenge yourself to shower in 5 minutes or less. Use a waterproof timer to track!",
            "points": 20,
            "estimatedImpact": "Saves ~40L water"
        },
        {
            "title": "🪥 Turn off tap while brushing",
            "details": "Don't let water run while brushing teeth. You can save up to 8L per minute!",
            "points": 10,
            "estimatedImpact": "Saves ~16L/brush"
        },
        {
            "title": "🔧 Fix dripping faucet",
            "details": "Check all faucets in your home and fix any drips. One drip per second wastes 20L daily!",
            "points": 15,
            "estimatedImpact": "Saves ~20L/day"
        },
        {
            "title": "🌧️ Collect rainwater",
            "details": "Set up a barrel or container to collect rainwater for watering plants.",
            "points": 15,
            "estimatedImpact": "Saves ~10L/use"
        },
        {
            "title": "🍽️ Run dishwasher when full",
            "details": "Wait until your dishwasher is completely full before running it. No half-loads!",
            "points": 10,
            "estimatedImpact": "Saves ~15L/load"
        },
        {
            "title": "🧊 Use a glass of water for brushing",
            "details": "Fill a glass with water for rinsing instead of running the tap.",
            "points": 5,
            "estimatedImpact": "Saves ~8L/day"
        },
        {
            "title": "🚿 Install low-flow showerhead",
            "details": "Modern low-flow showerheads maintain pressure while using 40% less water.",
            "points": 25,
            "estimatedImpact": "Saves ~60L/shower"
        },
        {
            "title": "🧺 Wash full loads of laundry",
            "details": "Only run washing machine with full loads. Saves water and energy!",
            "points": 15,
            "estimatedImpact": "Saves ~50L/load"
        },
        {
            "title": "🌱 Water plants in the morning",
            "details": "Early morning watering reduces evaporation, so plants get more water.",
            "points": 10,
            "estimatedImpact": "Saves ~30% water"
        },
        {
            "title": "🧽 Use a bowl to wash dishes",
            "details": "Fill a bowl with soapy water instead of running tap continuously.",
            "points": 10,
            "estimatedImpact": "Saves ~20L/session"
        },
    ],
    "Waste": [
        {
            "title": "♻️ Use a reusable bottle",
            "details": "Carry your own water bottle. Say no to single-use plastic bottles forever!",
            "points": 15,
            "estimatedImpact": "Saves 1 plastic bottle"
        },
        {
            "title": "🛍️ Bring reusable bag",
            "details": "Take your reusable shopping bag when going to the store. Keep one in your car!",
            "points": 10,
            "estimatedImpact": "Saves 1 plastic bag"
        },
        {
            "title": "🥬 Compost food scraps",
            "details": "Start composting fruit peels, vegetable scraps, and coffee grounds.",
            "points": 15,
            "estimatedImpact": "Reduces ~0.5kg waste"
        },
        {
            "title": "🥤 Refuse plastic straws",
            "details": "Say 'no straw, please' when ordering drinks, or bring your own reusable one.",
            "points": 5,
            "estimatedImpact": "Saves 1 plastic straw"
        },
        {
            "title": "📦 Recycle cardboard properly",
            "details": "Flatten boxes and put them in recycling. Remove tape and labels first!",
            "points": 10,
            "estimatedImpact": "Saves ~0.9kg CO₂/kg"
        },
        {
            "title": "🍱 Pack lunch in reusable containers",
            "details": "Stop using disposable packaging. Invest in good quality lunch containers.",
            "points": 15,
            "estimatedImpact": "Saves 5 items/day"
        },
        {
            "title": "☕ Use a reusable coffee cup",
            "details": "Bring your own cup to coffee shops. Many offer discounts too!",
            "points": 10,
            "estimatedImpact": "Saves 1 cup/day"
        },
        {
            "title": "🧻 Switch to cloth napkins",
            "details": "Replace paper napkins with cloth ones. Wash and reuse!",
            "points": 10,
            "estimatedImpact": "Saves paper waste"
        },
        {
            "title": "📄 Go paperless with bills",
            "details": "Switch to digital bills and statements. Save paper and reduce clutter!",
            "points": 5,
            "estimatedImpact": "Saves trees"
        },
        {
            "title": "🎁 Reuse gift bags and wrap",
            "details": "Save gift wrap, bags, and ribbons to reuse for future occasions.",
            "points": 10,
            "estimatedImpact": "Reduces waste"
        },
    ],
    "Transport": [
        {
            "title": "🚶 Walk short distances",
            "details": "For trips under 1km, leave the car at home and walk. Good for health and planet!",
            "points": 15,
            "estimatedImpact": "Saves ~0.2kg CO₂/km"
        },
        {
            "title": "🚌 Use public transport",
            "details": "Take the bus, metro, or tram instead of driving your car today.",
            "points": 20,
            "estimatedImpact": "Saves ~2.0kg CO₂/trip"
        },
        {
            "title": "🚲 Bike to work",
            "details": "Use your bicycle for your commute. Zero emissions and great exercise!",
            "points": 25,
            "estimatedImpact": "Saves ~3.0kg CO₂/trip"
        },
        {
            "title": "👥 Carpool with colleague",
            "details": "Share your ride to work with a colleague who lives nearby.",
            "points": 20,
            "estimatedImpact": "Saves 50% emissions"
        },
        {
            "title": "🏠 Work from home",
            "details": "Skip the commute by working from home today if your job allows.",
            "points": 25,
            "estimatedImpact": "Saves full commute"
        },
        {
            "title": "🛴 Use an e-scooter",
            "details": "Try an electric scooter for medium-distance trips instead of a car.",
            "points": 15,
            "estimatedImpact": "Saves ~1.5kg CO₂/trip"
        },
        {
            "title": "🚗 Maintain proper tire pressure",
            "details": "Check and inflate your tires to recommended PSI. Improves fuel efficiency by 3%!",
            "points": 10,
            "estimatedImpact": "Saves ~0.3kg CO₂/day"
        },
        {
            "title": "🛒 Combine errands into one trip",
            "details": "Plan your route to do multiple errands in one outing instead of several trips.",
            "points": 15,
            "estimatedImpact": "Saves ~1.0kg CO₂"
        },
        {
            "title": "✈️ Take train instead of plane",
            "details": "For distances under 500km, trains emit 10x less CO₂ than planes.",
            "points": 30,
            "estimatedImpact": "Saves ~5.0kg CO₂"
        },
        {
            "title": "💻 Video call instead of travel",
            "details": "Use video conferencing for meetings instead of traveling.",
            "points": 20,
            "estimatedImpact": "Saves travel emissions"
        },
    ]
}