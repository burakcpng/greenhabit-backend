"""
Learning content for eco-education
6 comprehensive articles on sustainability topics
"""

import uuid

LEARNING_ARTICLES = [
    {
        "id": str(uuid.uuid4()),
        "title": "Water Conservation at Home",
        "details": "Water is one of our most precious resources. Simple changes in daily habits can save thousands of liters per year. Fix leaky faucets - a single dripping faucet can waste up to 20 gallons per day. Take shorter showers - reducing your shower time by just 2 minutes can save up to 10 gallons of water. Turn off the tap while brushing teeth or shaving. Use a dishwasher instead of hand washing - modern dishwashers use less water. Collect rainwater for watering plants. Install low-flow showerheads and faucet aerators. Water your garden early morning or late evening to reduce evaporation. Choose drought-resistant plants for your garden. Use a broom instead of a hose to clean driveways.",
        "category": "Water"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Energy Efficiency Tips",
        "details": "Reducing energy consumption helps the environment and saves money. Switch to LED bulbs - they use 75% less energy than incandescent bulbs and last 25 times longer. Unplug electronics when not in use - standby power can account for 10% of household energy use. Use natural light when possible. Set your thermostat efficiently - each degree lower in winter saves about 3% on heating bills. Wash clothes in cold water - 90% of washing machine energy goes to heating water. Air dry clothes when possible. Use smart power strips to eliminate phantom loads. Seal windows and doors to prevent drafts. Consider solar panels for long-term savings. Choose energy-efficient appliances with high Energy Star ratings.",
        "category": "Energy"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Reducing Plastic Waste",
        "details": "Plastic pollution is one of the biggest environmental challenges. Over 8 million tons of plastic enter our oceans every year. Bring reusable bags when shopping. Use a reusable water bottle - the average person could save 167 plastic bottles per year. Say no to straws or use metal/bamboo alternatives. Choose products with minimal packaging. Buy in bulk to reduce packaging waste. Use beeswax wraps instead of plastic wrap. Choose bar soap and shampoo bars over bottled products. Recycle properly - learn what can and cannot be recycled in your area. Support businesses that use sustainable packaging. Participate in local beach or park cleanups.",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Sustainable Transportation",
        "details": "Transportation accounts for about 29% of greenhouse gas emissions. Walk or bike for short trips - it's healthy and emission-free. Use public transportation when possible. Carpool with colleagues or neighbors. If you drive, maintain your vehicle properly - properly inflated tires improve fuel efficiency. Combine errands into one trip to reduce total driving. Consider an electric or hybrid vehicle for your next car. Work from home when possible. Plan routes efficiently to avoid traffic and reduce fuel consumption. Fly less - one transatlantic flight can emit more CO2 than a year of driving. When flying is necessary, choose direct flights and offset your carbon.",
        "category": "Transport"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Composting 101",
        "details": "Composting turns food scraps and yard waste into nutrient-rich soil. About 30% of household waste can be composted. Start with a compost bin or designated area in your yard. Add 'green' materials like fruit and vegetable scraps, coffee grounds, and grass clippings. Balance with 'brown' materials like dried leaves, cardboard, and paper. Keep your compost moist but not wet. Turn it regularly to add oxygen. Avoid adding meat, dairy, or oily foods. Compost is ready when it's dark, crumbly, and smells earthy. Use it to enrich garden soil, potted plants, or lawn. Even apartment dwellers can compost with bokashi or vermicomposting methods.",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Understanding Your Carbon Footprint",
        "details": "A carbon footprint measures the total greenhouse gas emissions caused by an individual, event, organization, or product. The average person's carbon footprint in developed countries is about 10-20 tons of CO2 per year. Major contributors include: transportation (especially flying), home energy use, diet (meat production is carbon-intensive), and consumer goods. Calculate your footprint using online calculators to understand your impact. Reduce your footprint by: eating less meat, reducing air travel, improving home energy efficiency, buying local and seasonal products, reducing, reusing, and recycling. Carbon offsetting can help neutralize emissions you cannot eliminate. Small daily changes add up to significant impact over time.",
        "category": "General"
    }
]