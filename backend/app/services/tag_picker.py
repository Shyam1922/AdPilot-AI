"""Pick the 5 best hashtags for a post.

There is no live hashtag-popularity feed behind this, so we do not call the tags "trending". The 5 are chosen and
ordered by a fixed rule that matches how tags work: the brand's own tag first (it is the only one nobody competes
for), then a product-specific tag taken from the approved claims, then niche tags people in this category actually
browse, then a community tag, then a region tag. LinkedIn leans on professional tags, X on one or two broad ones.
"""
from __future__ import annotations

import re

# category family -> tags. niche = what shoppers browse, community = people-led tags, pro = LinkedIn audience.
_LIB: dict[str, dict[str, list[str]]] = {
    "skin": {"niche": ["#SkincareRoutine", "#SkincareIndia", "#GlowingSkin", "#SkincareTips"],
             "community": ["#SkincareCommunity", "#BeautyTips"], "pro": ["#Skincare", "#BeautyIndustry", "#D2C"]},
    "beauty": {"niche": ["#MakeupLovers", "#BeautyIndia", "#MakeupTips", "#Cosmetics"],
               "community": ["#BeautyCommunity", "#MakeupAddict"], "pro": ["#Beauty", "#BeautyIndustry", "#D2C"]},
    "food": {"niche": ["#FoodieIndia", "#HealthyEating", "#HomemadeFood", "#IndianFood"],
             "community": ["#FoodLovers", "#SnackTime"], "pro": ["#FoodTech", "#FoodIndustry", "#D2C"]},
    "beverage": {"niche": ["#CoffeeLovers", "#SpecialtyCoffee", "#CoffeeTime", "#TeaLovers"],
                 "community": ["#CoffeeCommunity", "#CoffeeAddict"], "pro": ["#Coffee", "#FoodAndBeverage", "#D2C"]},
    "fashion": {"niche": ["#IndianFashion", "#OOTD", "#SustainableFashion", "#EthnicWear"],
                "community": ["#FashionCommunity", "#StyleInspo"], "pro": ["#Fashion", "#FashionIndustry", "#D2C"]},
    "wellness": {"niche": ["#WellnessJourney", "#HealthyLiving", "#SelfCare", "#Wellness"],
                 "community": ["#WellnessCommunity", "#HealthyHabits"], "pro": ["#Wellness", "#HealthTech", "#D2C"]},
    "home": {"niche": ["#HomeDecor", "#HomeDecorIndia", "#InteriorStyling", "#HomeInspo"],
             "community": ["#HomeStyling", "#DecorLovers"], "pro": ["#HomeDecor", "#Retail", "#D2C"]},
    "generic": {"niche": ["#ShopLocal", "#SmallBusiness", "#NewLaunch", "#DesignedInIndia"],
                "community": ["#SupportSmallBusiness", "#ShopSmall"], "pro": ["#Startup", "#Entrepreneurship", "#D2C"]},
}
_FAMILY = [("skin", "skin"), ("sunscreen", "skin"), ("beauty", "beauty"), ("cosmetic", "beauty"), ("makeup", "beauty"),
           ("coffee", "beverage"), ("tea", "beverage"), ("beverage", "beverage"), ("drink", "beverage"),
           ("food", "food"), ("snack", "food"), ("fashion", "fashion"), ("apparel", "fashion"), ("cloth", "fashion"),
           ("wear", "fashion"), ("wellness", "wellness"), ("health", "wellness"), ("supplement", "wellness"),
           ("home", "home"), ("decor", "home"), ("furnish", "home")]
_INDIA = ["#MadeInIndia", "#StartupIndia"]


def family(category: str) -> str:
    c = (category or "").lower()
    return next((v for k, v in _FAMILY if k in c), "generic")


def _clean(tags: list[str]) -> list[str]:
    out = []
    for t in tags:
        t = "#" + re.sub(r"[^A-Za-z0-9]", "", t.lstrip("#"))
        if len(t) > 2 and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out


def pick(platform: str, brand: str, category: str, derived: list[str], india: bool, n: int = 5) -> list[str]:
    """`derived` is the tag list built from the brand's own claims (brand tag first). Returns exactly <= n tags."""
    fam = _LIB[family(category)]
    brand_tag = derived[0] if derived else "#" + re.sub(r"[^A-Za-z0-9]", "", brand)
    generic = {t.lower() for t in [*fam["niche"], *fam["pro"], *_INDIA, "#D2CIndia", "#ShopSmall"]}
    cat_tag = "#" + re.sub(r"[^A-Za-z0-9]", "", (category or "").split("&")[0].strip().title())
    plain = {cat_tag.lower(), ("#indian" + cat_tag[1:]).lower()}      # the category tag and its "#Indian..." twin
    specific = [t for t in derived[1:] if t.lower() not in generic and t.lower() not in plain]
    region = _INDIA if india else []
    if platform == "linkedin":
        order = [brand_tag, *fam["pro"][:2], *specific[:1], *region, *fam["niche"][:1], *fam["pro"][2:]]
    elif platform == "x":
        order = [brand_tag, *specific[:1], *fam["niche"][:1], *region[:1], *fam["pro"][:1], *fam["niche"][1:]]
    else:                                                              # instagram: discovery tags matter most
        order = [brand_tag, *specific[:1], *fam["niche"][:2], *fam["community"][:1], *region[:1],
                 *specific[1:], *fam["niche"][2:], *fam["community"][1:]]
    return _clean(order)[:n]
