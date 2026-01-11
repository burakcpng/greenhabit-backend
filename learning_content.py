"""
Comprehensive learning content for the GreenHabit app.
Includes 12+ deep-dive articles on sustainability, kitchen efficiency, and eco-education.
All content is professionally written in English.
"""

import uuid

LEARNING_ARTICLES = [
    {
        "id": str(uuid.uuid4()),
        "title": "Water Conservation: From Tap to Table",
        "details": """Water is our most precious resource, but much of our consumption is invisible. 

1. **At the Tap**: A single dripping faucet can waste up to 75 liters per day. Beyond fixing leaks, simple habits like turning off the tap while brushing teeth or using a bowl to wash vegetables (instead of running water) can save thousands of liters per year.
2. **Virtual Water**: This is the 'hidden' water used to produce food. For instance, 1kg of beef requires ~15,000 liters of water, whereas 1kg of potatoes requires only ~290 liters. 
3. **Smart Gardening**: Water plants early in the morning or late at night to reduce evaporation. Use drought-resistant local plants to maintain a beautiful garden without heavy irrigation.

Small changes in how we wash produce and what we choose to put on our plates can drastically reduce our total water footprint.""",
        "category": "Water"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Kitchen Energy Mastery",
        "details": """The kitchen is the energy heart of the home. Optimizing appliance use is key to lowering your utility bills and carbon emissions.

- **Refrigeration**: Keep coils clean and ensure door seals are airtight. A fridge that isn't sealed properly can waste up to 30% more energy. 
- **The Oven Rule**: Avoid 'peeking'—opening the oven door drops the temperature by 25°C instantly. Whenever possible, use an air fryer or microwave for smaller portions as they are significantly more efficient.
- **Cooking with Lids**: Always use a lid on pots. It traps heat, allowing water to boil faster and food to simmer at lower energy settings.
- **LED Lighting**: If your kitchen still uses old bulbs, switching to LEDs can reduce lighting energy use by 75% and they last 25 times longer.""",
        "category": "Energy"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Science of Composting & Soil Health",
        "details": """Composting turns kitchen 'waste' into nutrient-rich soil, preventing methane emissions in landfills.

**The Golden Mix**:
- **Greens (Nitrogen)**: Vegetable scraps, fruit peels, coffee grounds.
- **Browns (Carbon)**: Dried leaves, cardboard, shredded paper.
Maintain a 2:1 ratio of Browns to Greens for a healthy, odorless pile.

**Apartment Solutions**: If you don't have a yard, consider 'Bokashi' (fermentation) or 'Vermicomposting' (worm bins). These compact systems allow urban dwellers to recycle organic waste efficiently. Composting not only reduces your trash volume by 30% but also provides the best natural fertilizer for your houseplants or balcony garden.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Understanding Date Labels & Food Safety",
        "details": """Misunderstanding date labels is a leading cause of preventable food waste. 

- **'Use By'**: This is about safety. Do not eat food past this date, but you can freeze it *on* the date to save it for later.
- **'Best Before'**: This is about quality. The food is still safe to eat after this date, but it might lose some texture or flavor. Canned goods and dry pasta are safe for months or even years past this date if the packaging is intact.
- **The Senses Test**: Trust your nose and eyes. If bread isn't moldy or milk doesn't smell sour, it's often still good to use. Organising your fridge with a 'First In, First Out' (FIFO) system ensures older items are used before they expire.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Food Miles: The True Cost of Distance",
        "details": """The average meal travels over 2,000 kilometers before reaching your fork. This transport contributes heavily to global CO2 levels.

- **Seasonal Eating**: Buying food when it naturally grows in your region reduces the need for energy-intensive greenhouses and long-distance refrigerated shipping.
- **Support Local**: Shopping at farmers' markets supports local agriculture and reduces the packaging needed for long-haul transport.
- **Air-Freighted Foods**: Highly perishable out-of-season items (like berries in winter) are often flown in, creating 50x more emissions than sea shipping. Choosing 'sea-shipped' or frozen seasonal produce is a much greener alternative.""",
        "category": "Transport"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Zero-Waste Shopping Guide",
        "details": """Waste management starts at the grocery store. Transitioning to a zero-waste shopping habit involves preparation and mindfulness.

1. **Reusable Kits**: Always keep a few tote bags and small cotton produce bags in your car or by the door. Refusing a single plastic bag prevents 500 years of environmental pollution.
2. **Bulk Buying**: Look for stores that offer dry goods like grains, nuts, and spices in bulk bins. You can bring your own jars and fill only what you need, reducing both food and packaging waste.
3. **Concentrated Refills**: For cleaning supplies, choose concentrated liquids that you mix with water at home. This reduces the weight and volume of plastic being transported globally.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Impact of Microplastics in the Kitchen",
        "details": """Microplastics are tiny plastic particles less than 5mm in size. They have infiltrated our food chain, largely through the tools we use in the kitchen.

- **Cutting Boards**: Plastic cutting boards shed millions of microparticles into your food during chopping. Switch to wood or bamboo boards.
- **Tea Bags**: Many modern tea bags are sealed with plastic, releasing billions of microplastics into a single cup of hot tea. Use loose-leaf tea with a stainless steel infuser.
- **Storage**: When plastic containers are heated, chemicals and microplastics leach into food. Transition to glass or stainless steel storage containers.
- **Tap Water**: Use a high-quality water filter to catch microplastics that may be present in municipal water supplies.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Plant-Based Power: Diet and CO2",
        "details": """Your dietary choices are one of your strongest levers for environmental change. Animal agriculture is responsible for nearly 15% of global greenhouse gas emissions.

- **The Beef Factor**: Beef production creates roughly 10 times more emissions than poultry or pork, and nearly 30-50 times more than legumes like lentils or beans.
- **Methane Emissions**: Livestock produce methane, which is far more potent than CO2 in the short term.
- **Land Use**: Growing crops to feed animals is inefficient. We can feed more people with less land by consuming plants directly.
Even participating in 'Meatless Mondays' can reduce your individual carbon footprint by hundreds of kilograms per year.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Eco-Friendly Cleaning: Nature's Chemistry",
        "details": """Most commercial cleaning products contain harsh chemicals that eventually wash into our waterways, harming aquatic life.

- **Vinegar**: A natural disinfectant and grease-cutter. Use it to clean glass, countertops, and even as a fabric softener.
- **Baking Soda**: Excellent for scrubbing stains and absorbing odors in the fridge or trash bins.
- **Citrus Peels**: Infuse vinegar with lemon or orange peels for a powerful, fresh-smelling all-purpose cleaner.
- **Castile Soap**: A biodegradable, plant-based soap that can be used for everything from dishes to hand-washing.
Switching to natural cleaners reduces indoor air pollution and keeps toxic runoff out of our ecosystems.""",
        "category": "Water"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Hidden Energy of Hot Water",
        "details": """Heating water is typically the second largest energy expense in a household.

- **Wash Cold**: About 90% of the energy used by a washing machine goes toward heating the water. Modern detergents are designed to work perfectly in cold water.
- **Shower Habits**: Reducing your shower temperature just slightly and installing a low-flow showerhead can save significant energy and water.
- **Dishwashers**: Always wait for a full load. Modern dishwashers are actually more water-efficient than hand-washing, but only when used at full capacity.
- **Pipe Insulation**: Insulating your hot water pipes ensures that heat isn't lost as the water travels to your faucet.""",
        "category": "Energy"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Circular Economy: Repair over Replace",
        "details": """Our current 'Take-Make-Waste' model is unsustainable. A circular economy focuses on keeping items in use for as long as possible.

- **Kitchen Appliances**: Before throwing away a broken toaster or blender, check if it can be repaired. Many cities have 'Repair Cafés' where volunteers help fix small electronics.
- **Sharp Knives**: Regularly sharpening your kitchen knives prevents you from buying new ones and makes cooking safer and faster.
- **Cast Iron Longevity**: Quality cookware like cast iron can last for generations if properly seasoned and maintained, reducing the need for non-stick pans that degrade quickly.
Embracing a 'repair first' mindset reduces the demand for new manufacturing and the resulting industrial emissions.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Sustainable Seafood: Protecting our Oceans",
        "details": """Overfishing is a critical threat to ocean biodiversity. As a consumer, your choices at the fish counter matter.

- **Certifications**: Look for the MSC (Marine Stewardship Council) or ASC (Aquaculture Stewardship Council) labels to ensure the fish was caught or farmed responsibly.
- **Eat Lower on the Food Chain**: Small fish like sardines and mackerel are more sustainable and contain fewer heavy metals than large predators like tuna or swordfish.
- **Bycatch Issues**: Avoid species caught using destructive methods like bottom trawling, which destroys seafloor habitats and kills non-target species.
- **Seasonal Fish**: Just like produce, different fish species have seasons. Buying in-season helps maintain healthy population levels during spawning periods.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Understanding Your Carbon Footprint",
        "details": """A carbon footprint is the total amount of greenhouse gases (including methane and nitrous oxide) that are generated by our actions.

- **The 2-Ton Goal**: Currently, the average person in high-income countries has a footprint of 10-15 tons. To meet global climate goals, we need to bring this down to under 2 tons by 2050.
- **Direct vs. Indirect**: Direct emissions come from things you control (your car, your heating). Indirect emissions come from the production of things you buy (your phone, your clothes, your food).
- **Measurement**: Use the GreenHabit app to identify which areas of your life—transport, diet, or energy—are the biggest contributors. Small, consistent changes are more effective than temporary drastic ones.""",
        "category": "General"
    }
]