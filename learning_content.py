"""
Comprehensive learning content for the GreenHabit app.
Includes ~30 deep-dive articles on sustainability, ecology, and scientific facts.
All content is professionally written in English for a global audience.
"""

import uuid

LEARNING_ARTICLES = [
    # --- WATER & OCEANS ---
    {
        "id": str(uuid.uuid4()),
        "title": "Virtual Water: The Invisible Consumption",
        "details": """The water running from your tap is just the tip of the iceberg. 'Virtual Water' is the total amount of water used to produce a product.

- **A Pair of Jeans:** From growing the cotton to dyeing the fabric, a single pair of jeans requires about **10,000 liters** of water.
- **A Cup of Coffee:** It takes **140 liters** of water to grow, process, and transport the beans for just one morning cup.
- **Solution:** Buying fewer, higher-quality clothes and preventing food waste saves far more water than just turning off the tap.""",
        "category": "Water"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "What is Ocean Acidification?",
        "details": """Oceans absorb about 30% of the carbon dioxide (CO2) in the atmosphere. While this helps regulate the climate, excess CO2 changes the chemistry of seawater, making it more acidic.

- **The Danger:** Acidic water depletes carbonate ions, making it difficult for corals, mussels, and plankton to build their shells.
- **Chain Reaction:** If plankton populations collapse, the fish that feed on them will starve, threatening the entire marine ecosystem.""",
        "category": "Water"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Microplastics: Plastic on Our Plates",
        "details": """Microplastics are plastic particles smaller than 5mm. Plastics in the ocean eventually break down into these tiny pieces, are eaten by fish, and enter our food chain.

- **Scientific Fact:** Research suggests the average person ingests about **5 grams** of plastic (roughly the weight of a credit card) every week.
- **Sources:** Synthetic clothing fibers from washing machines, tire wear dust, and degraded single-use plastics.""",
        "category": "Water"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Science of Rainwater Harvesting",
        "details": """Rainwater is often healthier for plants than tap water because it is free of chlorine and fluoride, and has an ideal pH level.

- **Potential:** On a 100 square meter roof, just 1mm of rainfall yields **100 liters** of water.
- **Usage:** Beyond gardening, using filtered rainwater for toilet flushing can reduce household potable water consumption by up to 40%.""",
        "category": "Water"
    },

    # --- ENERGY & CLIMATE ---
    {
        "id": str(uuid.uuid4()),
        "title": "Vampire Energy (Standby Power)",
        "details": """Appliances continue to consume electricity even when turned off if they remain plugged in. This is called 'Vampire Energy' or 'Phantom Load'.

- **Data:** In the average home, **10%** of the electricity bill comes from devices in standby mode.
- **Culprits:** TVs, microwaves (digital clocks), computers, and phone chargers.
- **Solution:** Use smart power strips to cut power to all devices with a single switch.""",
        "category": "Energy"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Miracle of LED Technology",
        "details": """Old incandescent bulbs converted 90% of energy into heat, not light. LEDs work on the opposite principle.

- **Efficiency:** LEDs use 80-90% less energy than incandescent bulbs.
- **Lifespan:** An LED bulb can last 25,000 hours, while an incandescent lasts only about 1,000 hours.
- **Cooling:** Because they emit less heat, they also reduce air conditioning loads in the summer.""",
        "category": "Energy"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Greenhouse Effect: Methane vs. CO2",
        "details": """Greenhouse gases blanket the Earth, trapping solar heat. However, since the industrial revolution, this blanket has become too thick.

- **Potency:** While Methane stays in the atmosphere for a shorter time than CO2, it traps heat **25 times** more effectively over a 100-year period.
- **Sources:** Major methane sources include livestock agriculture, rice paddies, and decomposing waste in landfills.""",
        "category": "Energy"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Carbon Cost of Data Centers",
        "details": """The internet doesn't live in a fluffy 'cloud'; it lives in massive physical data centers. Every email, video stream, and AI query consumes energy.

- **Fact:** Data centers account for about 1-2% of global electricity consumption.
- **Digital Hygiene:** Deleting unnecessary emails and emptying your spam folder reduces server load and the energy needed for cooling and storage.""",
        "category": "Energy"
    },

    # --- FOOD & AGRICULTURE ---
    {
        "id": str(uuid.uuid4()),
        "title": "If Food Waste Were a Country...",
        "details": """If food waste were a country, it would be the **third-largest** emitter of greenhouse gases in the world, after China and the USA.

- **Rotting Food:** Food rotting in landfills without oxygen produces Methane, a potent greenhouse gas.
- **Resource Waste:** Throwing away an apple also means throwing away the water, labor, and transport fuel used to grow it.""",
        "category": "Food"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Resource Intensity of Meat",
        "details": """Animal agriculture consumes a disproportionate amount of resources compared to plant-based agriculture.

- **Land Use:** Livestock takes up 77% of global agricultural land but produces only 18% of the world's calories.
- **Conversion:** It takes roughly 25 calories of plant feed to produce just 1 calorie of beef.
- **Water:** Producing 1kg of beef requires ~15,000 liters of water, while 1kg of lentils requires only ~50 liters.""",
        "category": "Food"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Understanding Food Miles",
        "details": """'Food Miles' measure the distance food travels from farm to fork.

- **Air vs. Sea:** Highly perishable fruits flown in out-of-season (e.g., berries in winter) can cause 50x more emissions than bananas shipped by sea.
- **Seasonality:** Eating locally and seasonally eliminates the need for energy-intensive heated greenhouses and long-haul transport.""",
        "category": "Food"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Soil Health as a Carbon Sink",
        "details": """Healthy soil is one of the world's largest carbon reservoirs.

- **Regenerative Ag:** No-till farming preserves soil structure, sequestering carbon underground instead of releasing it.
- **Pesticides:** Excessive chemical use kills microscopic soil life, reducing the soil's ability to hold water and leading to erosion.""",
        "category": "Food"
    },

    # --- WASTE & CIRCULAR ECONOMY ---
    {
        "id": str(uuid.uuid4()),
        "title": "The Half-Life of Plastic",
        "details": """Plastic does not biodegrade; it only photodegrades into smaller pieces (microplastics).

- **Timelines:**
  - Plastic bottle: 450 years
  - Disposable diaper: 500 years
  - Fishing line: 600 years
- **Fact:** Virtually every piece of plastic ever made still exists in some form today.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "What is the Circular Economy?",
        "details": """Our current system is 'Take-Make-Waste' (Linear). A circular economy mimics nature; there is no waste, only feedstock for the next cycle.

- **Principles:**
  1. Design out waste and pollution.
  2. Keep products and materials in use (Repair, Reuse).
  3. Regenerate natural systems.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Urban Mine: E-Waste",
        "details": """Old phones and laptops aren't trash; they are high-grade metal ores.

- **Value:** There is 100 times more gold in a ton of smartphones than in a ton of gold ore.
- **Danger:** When recycled improperly, toxic materials like lead and mercury can leach into soil and groundwater.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Truth About Fast Fashion",
        "details": """The fashion industry generates more carbon emissions than all international flights and maritime shipping combined.

- **Synthetics:** 60% of clothing materials are plastic (polyester, nylon).
- **Dyes:** Textile dyeing is the second largest polluter of water globally.
- **Usage:** Extending the life of a garment by just 9 months reduces its carbon and water footprints by 20-30%.""",
        "category": "Waste"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Chemistry of Composting",
        "details": """Composting is the aerobic decomposition of organic matter by microorganisms.

- **Greens (Nitrogen):** Vegetable peels, coffee grounds.
- **Browns (Carbon):** Dry leaves, cardboard, twigs.
- **Result:** The right mix (1 Green : 2 Browns) transforms waste into nutrient-rich humus and prevents methane formation in landfills.""",
        "category": "Waste"
    },

    # --- TRANSPORT & CITIES ---
    {
        "id": str(uuid.uuid4()),
        "title": "EVs and the Carbon Debt",
        "details": """Electric Vehicles (EVs) have zero tailpipe emissions, but manufacturing their batteries is carbon-intensive.

- **Break-even Point:** An EV typically offsets its higher manufacturing emissions after 20,000 - 30,000 km of driving compared to a gas car.
- **The Grid:** An EV gets cleaner as the energy grid gets cleaner (shifting from coal to wind/solar).""",
        "category": "Transport"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Efficiency of the Bicycle",
        "details": """The bicycle is the most efficient machine ever created for converting human energy into motion.

- **Energy:** A cyclist travels 3 times faster and 4 times further than a pedestrian using the same amount of energy.
- **Space:** You can park 10-12 bicycles in a single car parking space. Micromobility is the key to solving urban congestion.""",
        "category": "Transport"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Urban Heat Island Effect",
        "details": """City centers are often 1-3°C hotter than surrounding rural areas. This is the 'Urban Heat Island' effect.

- **Causes:** Concrete and asphalt absorb and retain heat. Lack of greenery reduces cooling via evaporation.
- **Solution:** Green roofs, lighter-colored pavements, and urban trees can significantly cool cities and reduce air conditioning needs.""",
        "category": "Transport"
    },

    # --- BIODIVERSITY & NATURE ---
    {
        "id": str(uuid.uuid4()),
        "title": "Why Bees Matter",
        "details": """Bees don't just make honey; they are the guarantors of global food security.

- **Pollination:** 1 in every 3 bites of food we eat (fruits, vegetables, nuts) depends on pollinators.
- **Threat:** Pesticides and habitat loss are driving bee populations down. Planting bee-friendly flowers (like lavender or thyme) can help restore local populations.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "How Trees Cool the Planet",
        "details": """Trees are nature's air conditioners.

- **Shade:** They block direct sunlight, keeping surfaces cool.
- **Transpiration:** Trees release water vapor through their leaves, which cools the surrounding air.
- **Impact:** A strategically planted tree can reduce a home's air conditioning needs by up to 30%.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Deforestation and the Amazon",
        "details": """The Amazon rainforest is often called the 'Lungs of the Earth', but it's more accurately the 'Earth's Air Conditioner'.

- **Carbon Storage:** Trees absorb carbon as they grow. When cut or burned, that stored carbon is released back into the atmosphere.
- **Rain:** The Amazon generates its own rainfall. Deforestation can disrupt this cycle, turning the rainforest into a savannah.""",
        "category": "General"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Importance of Biodiversity",
        "details": """Biodiversity is the variety of life in an ecosystem. The more diverse an ecosystem, the more resilient it is to disease and climate change.

- **Example:** A forest with only one type of tree (monoculture) can be wiped out by a single pest, whereas a diverse forest survives.
- **Human Benefit:** Over 50% of modern medicines are derived from nature and plants.""",
        "category": "General"
    },

    # --- SOCIAL & PSYCHOLOGY ---
    {
        "id": str(uuid.uuid4()),
        "title": "Dealing with Eco-Anxiety",
        "details": """Eco-anxiety is the chronic fear of environmental doom.

- **Coping:** The best antidote to anxiety is action. reducing your individual footprint, joining local community groups, and focusing on controllable variables builds psychological resilience.""",
        "category": "Social"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Spotting Greenwashing",
        "details": """Greenwashing is a marketing strategy where companies deceptively claim their products are eco-friendly.

- **Tips:** Be skeptical of vague terms like "Natural" or "Eco-friendly" without definitions.
- **Proof:** Look for third-party certifications (FSC, Organic, Fair Trade). A green package does not mean a green product.""",
        "category": "Social"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Minimalism as Sustainability",
        "details": """Minimalism isn't just about owning less; it's about intentional consumption.

- **Connection:** Buying less directly reduces emissions from manufacturing and transport.
- **Quality:** Focusing on quality over quantity and buying durable goods prevents waste from entering landfills.""",
        "category": "Social"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "Why Fair Trade Matters",
        "details": """Sustainability is about people as well as the planet.

- **Definition:** Fair Trade ensures producers (especially for coffee, cocoa, bananas) are paid a living wage and no child labor is used.
- **Link:** You cannot protect forests without fighting poverty, as impoverished communities may be forced to exploit natural resources to survive.""",
        "category": "Social"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Sharing Economy",
        "details": """An economic model defined by access to goods rather than ownership.

- **Examples:** Car-sharing, tool libraries, peer-to-peer rentals.
- **Benefit:** If you only need a drill for 15 minutes a year, you don't need to own one. Sharing reduces the demand for raw materials and manufacturing.""",
        "category": "Social"
    },
    {
        "id": str(uuid.uuid4()),
        "title": "The Power of Individual Action",
        "details": """'What can I do alone?' is a common fallacy.

- **Social Proof:** Your actions influence your social circle. If you install solar panels, your neighbors are more likely to do the same.
- **Market Signals:** As consumer demand shifts (e.g., for organic food or EVs), massive corporations are forced to change their production models.""",
        "category": "Social"
    }
]