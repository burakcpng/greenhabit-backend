import re

class ProfanityFilter:
    """
    Basic profanity filter for UGC compliance (Apple Guideline 1.2).
    Blocks explicit/offensive terms in English and Turkish.
    """
    
    # Combined blocklist for simplicity
    BANNED_WORDS = {
    
       # English Common
        "fuck", "shit", "bitch", "asshole", "dick", "pussy", "bastard", "cunt",
        "whore", "slut", "faggot", "nigger", "retard", "rape", "incest",
        "cocaine", "heroin", "meth", "nazi", "hitler", "2g1c", "2 girls 1 cup", "acrotomophilia", "alabama hot pocket",
        "alaskan pipeline", "anal", "anilingus", "anus", "apeshit", "arsehole",
        "ass", "assmunch", "auto erotic", "autoerotic", "babeland",
        "baby batter", "baby juice", "ball gag", "ball gravy", "ball kicking",
        "ball licking", "ball sack", "ball sucking", "bangbros", "bareback",
        "barely legal", "barenaked", "bastardo", "bastinado", "bbw", "bdsm",
        "beaner", "beaners", "beaver cleaver", "beaver lips", "bestiality",
        "big black", "big breasts", "big knockers", "big tits", "bimbos",
        "birdlock", "bitches", "black cock", "blonde action",
        "blonde on blonde action", "blowjob", "blow job", "blow your load",
        "blue waffle", "blumpkin", "bollocks", "bondage", "boner", "boob",
        "boobs", "booty call", "brown showers", "brunette action", "bukkake",
        "bulldyke", "bullet vibe", "bullshit", "bung hole", "bunghole",
        "busty", "butt", "buttcheeks", "butthole", "camel toe", "camgirl",
        "camslut", "camwhore", "carpet muncher", "carpetmuncher",
        "chocolate rosebuds", "circlejerk", "cleveland steamer", "clit",
        "clitoris", "clover clamps", "clusterfuck", "cock", "cocks",
        "coprolagnia", "coprophilia", "cornhole", "coon", "coons",
        "creampie", "cum", "cumming", "cunnilingus", "darkie",
        "date rape", "daterape", "deep throat", "deepthroat",
        "dendrophilia", "dildo", "dingleberry", "dingleberries",
        "dirty pillows", "dirty sanchez", "doggie style", "doggiestyle",
        "doggy style", "doggystyle", "dog style", "dolcett", "domination",
        "dominatrix", "dommes", "donkey punch", "double dong",
        "double penetration", "dp action", "dry hump", "dvda",
        "eat my ass", "ecchi", "ejaculation", "erotic", "erotism", "escort",
        "eunuch", "fecal", "felch", "fellatio", "feltch",
        "female squirting", "femdom", "figging", "fingerbang", "fingering",
        "fisting", "foot fetish", "footjob", "frotting", "fuck buttons",
        "fuckin", "fucking", "fucktards", "fudge packer", "fudgepacker",
        "futanari", "gang bang", "gay sex", "genitals", "giant cock",
        "girl on", "girl on top", "girls gone wild", "goatcx", "goatse",
        "god damn", "gokkun", "golden shower", "goodpoop", "goo girl",
        "goregasm", "grope", "group sex", "g-spot", "guro", "hand job",
        "handjob", "hard core", "hardcore", "hentai", "homoerotic",
        "honkey", "hooker", "hot carl", "hot chick", "how to kill",
        "how to murder", "huge fat", "humping", "intercourse", "jack off",
        "jail bait", "jailbait", "jelly donut", "jerk off", "jigaboo",
        "jiggaboo", "jiggerboo", "jizz", "juggs", "kike", "kinbaku",
        "kinkster", "kinky", "knobbing", "leather restraint",
        "leather straight jacket", "lemon party", "lolita", "lovemaking",
        "make me come", "male squirting", "masturbate", "menage a trois",
        "milf", "missionary position", "motherfucker", "mound of venus",
        "mr hands", "muff diver", "muffdiving", "nambla", "nawashi",
        "negro", "neonazi", "nigga", "nig nog", "nimphomania", "nipple",
        "nipples", "nsfw images", "nude", "nudity", "nympho",
        "nymphomania", "octopussy", "omorashi", "one cup two girls",
        "one guy one jar", "orgasm", "orgy", "paedophile", "paki",
        "panties", "panty", "pedobear", "pedophile", "pegging", "penis",
        "phone sex", "piece of shit", "pissing", "piss pig", "pisspig",
        "playboy", "pleasure chest", "pole smoker", "ponyplay", "poof",
        "poon", "poontang", "punany", "poop chute", "poopchute", "porn",
        "porno", "pornography", "prince albert piercing", "pthc",
        "pubes", "queaf", "queef", "quim", "raghead", "raging boner",
        "raping", "rapist", "rectum", "reverse cowgirl", "rimjob",
        "rimming", "rosy palm", "rosy palm and her 5 sisters",
        "rusty trombone", "sadism", "santorum", "scat", "schlong",
        "scissoring", "semen", "sex", "sexo", "sexy", "shaved beaver",
        "shaved pussy", "shemale", "shibari", "shitblimp", "shitty",
        "shota", "shrimping", "skeet", "slanteye", "s&m", "smut",
        "snatch", "snowballing", "sodomize", "sodomy", "spic",
        "splooge", "splooge moose", "spooge", "spread legs", "spunk",
        "strap on", "strapon", "strappado", "strip club", "style doggy",
        "suck", "sucks", "suicide girls", "sultry women", "swastika",
        "swinger", "tainted love", "taste my", "tea bagging", "threesome",
        "throating", "tied up", "tight white", "tit", "tits", "titties",
        "titty", "tongue in a", "topless", "tosser", "towelhead",
        "tranny", "tribadism", "tub girl", "tubgirl", "tushy", "twat",
        "twink", "twinkie", "two girls one cup", "undressing", "upskirt",
        "urethra play", "urophilia", "vagina", "venus mound", "vibrator",
        "violet wand", "vorarephilia", "voyeur", "vulva", "wank",
        "wetback", "wet dream", "white power", "wrapping men",
        "wrinkled starfish", "xx", "xxx", "yaoi", "yellow showers",
        "yiffy", "zoophilia", "🖕",
        
        # Turkish Common
        "amk", "aq", "siktir", "pic", "piç", "yarak", "yarrak", "orospu", "oç", "oc",
        "sik", "sokuk", "kahpe", "kaltak", "gavat", "ibne", "göt", "sikik", "yavşak",
        "amina", "amına" , "amcik" , "bacısiken" , "kaşar" , "gevende" , "döl" , "zenci" ,
        "penci" ,"zorno" , "bacını" , "ananı" , "anne" , "babanne" , "sakso" , "taşak" ,
        "taşşak" , "sıç" , "sıçmak" ,
    }

    # ── Leet-speak, per word ────────────────────────────────────────────────
    # Digits and symbols are read as letters only inside a word that has
    # letters in it ("sh1t", "b4d", "$hit", "@sshole"). Left alone: words
    # without letters ("30", "10,000", "23:00", "100%", "&") and a number
    # followed by a unit ("5km", "10k", "2l", "1.5kg", "19°c", "8h"), so habit
    # titles with numbers are never read as words.
    # Same rule, map and units as the iOS ContentSafetyFilter.swift.

    LEET_MAP = {
        "0": "o", "1": "i", "2": "z", "3": "e", "4": "a", "5": "s", "6": "g", "7": "t", "8": "b", "9": "g",
        "@": "a", "$": "s", "!": "i", "|": "i", "+": "t", "(": "c", "<": "c", "{": "c", "[": "c", "]": "i",
        "^": "a", "`": "a", "~": "n", "%": "x", "#": "h", "&": "a",
        "€": "e", "£": "l", "ß": "b", "×": "x", "°": "o",
    }

    NUMBER_UNITS = {
        "k", "km", "m", "mi", "cm", "mm", "ft", "yd",
        "l", "ml", "cl", "dl", "kg", "g", "mg", "lb", "lbs", "oz",
        "s", "sec", "secs", "min", "mins", "h", "hr", "hrs", "d", "w", "wk", "wks", "y", "yr", "yrs",
        "x", "st", "nd", "rd", "th", "am", "pm",
        "kwh", "wh", "kw", "mph", "kmh", "kph", "cal", "kcal", "°", "°c", "°f", "c", "f",
        "gb", "mb", "tb", "p", "pcs", "pc",
    }

    _NUMBER_WITH_UNIT = re.compile(r"^[0-9][0-9.,:]*(?P<unit>.*)$")
    _EDGE_PUNCTUATION = re.compile(r"^[^\w°]+|[^\w°]+$")

    @staticmethod
    def is_number_with_unit(token: str) -> bool:
        """'5km', '10k', '1.5kg', '19°c', '8h', also with surrounding punctuation."""
        core = ProfanityFilter._EDGE_PUNCTUATION.sub("", token)
        match = ProfanityFilter._NUMBER_WITH_UNIT.match(core)
        return bool(match) and match.group("unit") in ProfanityFilter.NUMBER_UNITS

    @staticmethod
    def substitute_leet(token: str) -> str:
        """`token` is one lowercased word."""
        if not any(ch.isalpha() for ch in token):
            return token
        if ProfanityFilter.is_number_with_unit(token):
            return token
        return "".join(ProfanityFilter.LEET_MAP.get(ch, ch) for ch in token)

    @staticmethod
    def is_safe(text: str) -> bool:
        """
        Returns True if text is safe (no banned words).
        Returns False if text contains banned words.
        """
        if not text:
            return True
            
        # Normalize: lowercase, then leet-speak word by word
        cleaned_text = " ".join(ProfanityFilter.substitute_leet(t) for t in text.lower().split())
        
        # Check against blocklist using word boundaries
        words = re.findall(r'\b\w+\b', cleaned_text)
        
        for word in words:
            if word in ProfanityFilter.BANNED_WORDS:
                return False

        # Entries that are not words (e.g. the middle-finger emoji)
        for entry in ProfanityFilter._NON_WORD_ENTRIES:
            if entry in cleaned_text:
                return False
                
        return True

    @staticmethod
    def validate_content(text: str, context: str = "Content") -> None:
        """
        Raises generic ValueError if content is unsafe.
        Used for quick validation.
        """
        if not ProfanityFilter.is_safe(text):
            raise ValueError(f"{context} contains inappropriate language and cannot be saved.")


ProfanityFilter._NON_WORD_ENTRIES = {w for w in ProfanityFilter.BANNED_WORDS if not re.search(r"\w", w)}
