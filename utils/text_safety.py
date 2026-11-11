import re
import unicodedata

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

        # Common inflected forms (whole words only: list the forms themselves)
        "fucked", "fucker", "fucks", "dickhead", "cocksucker", "wanker",
        "siktirgit", "sikerim", "sikeyim", "orospular", "orospunun", "piçler", "götveren",

        # Czech (with and without diacritics)
        "kurva", "kurvo", "kurvy", "kurvě", "píča", "píčo", "pica", "pico", "kokot", "kokote", "kokoti",
        "čurák", "curak", "hovno", "hovna", "prdel", "mrdat", "mrdka", "šukat", "sukat", "zmrd", "zmrde",
        "hajzl", "hajzle", "kunda", "děvka", "devka", "buzerant", "debil", "zkurvysyn",
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

    # Lookalike letters from other scripts (same table as the iOS filter).
    HOMOGLYPHS = {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ѕ": "s", "ј": "j",
        "ԁ": "d", "ԛ": "q", "ԝ": "w", "ѵ": "v", "ո": "n",
        "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "n", "ο": "o", "ρ": "p", "τ": "t", "υ": "y",
        "χ": "x", "η": "n", "θ": "o", "μ": "m", "ω": "w",
        "ｆ": "f", "ｕ": "u", "ｃ": "c", "ｋ": "k",
    }
    _ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff\u00ad\u2060\u180e]")
    _WORD_PIECE = re.compile(r"[^\W_]+")

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

    # Entries that match only as written, never after removing diacritics,
    # because a word of another language folds onto them: Czech "nudě"
    # (boredom) → "nude". (Turkish "sık" keeps its dotless ı, so it never
    # becomes "sik".)
    AS_WRITTEN_ONLY = {"nude"}

    @staticmethod
    def plain(word: str) -> str:
        """The word without diacritics ("fück" → "fuck"). Dotless "ı" stays."""
        decomposed = unicodedata.normalize("NFD", word)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    @staticmethod
    def words(text: str) -> list:
        """
        The words of `text`, lowercased, with lookalike letters and leet-speak
        resolved. Separators inside a word are dropped ("f.u.c.k" → "fuck") and
        runs of single letters are joined ("s h i t" → "shit").
        """
        cleaned = ProfanityFilter._ZERO_WIDTH.sub("", text).lower()
        cleaned = "".join(ProfanityFilter.HOMOGLYPHS.get(ch, ch) for ch in cleaned)
        cleaned = " ".join(ProfanityFilter.substitute_leet(t) for t in cleaned.split())
        words, letters = [], ""
        for piece in ProfanityFilter._WORD_PIECE.findall(cleaned):
            if len(piece) == 1:
                letters += piece
                continue
            if letters:
                words.append(letters)
                letters = ""
            words.append(piece)
        if letters:
            words.append(letters)
        return words

    @staticmethod
    def _is_banned(word: str) -> bool:
        # As written, or without diacritics against the entries that have none
        # ("fück" → "fuck"; "göt" stays "göt", so English "got" is never hit).
        return word in ProfanityFilter.BANNED_WORDS or ProfanityFilter.plain(word) in ProfanityFilter._ASCII_ENTRIES

    @staticmethod
    def is_safe(text: str) -> bool:
        """
        Returns True if text is safe (no banned words).
        Returns False if text contains banned words.
        Whole words only: a banned word inside another word does not count.
        """
        if not text:
            return True

        words = ProfanityFilter.words(text)
        if any(ProfanityFilter._is_banned(word) for word in words):
            return False

        # A word split into short pieces ("fu ck", "sh it"). The pieces must
        # join to exactly a banned word ("go to" is not "got").
        for size in (2, 3, 4):
            for start in range(len(words) - size + 1):
                window = words[start:start + size]
                if all(len(piece) <= 3 for piece in window) and ProfanityFilter._is_banned("".join(window)):
                    return False

        # Entries that are not words (e.g. the middle-finger emoji)
        lowered = text.lower()
        for entry in ProfanityFilter._NON_WORD_ENTRIES:
            if entry in lowered:
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
ProfanityFilter._ASCII_ENTRIES = {
    w for w in ProfanityFilter.BANNED_WORDS if w.isascii() and w not in ProfanityFilter.AS_WRITTEN_ONLY
}
